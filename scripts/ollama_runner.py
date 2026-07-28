#!/usr/bin/env python3
"""Run the entire bilingual pipeline against a local Ollama model.

This companion avoids hundreds of agent tool turns for long documents while
keeping all semantic work on the user's local Ollama instance. It is fully
checkpointed through document_pipeline.py and can be rerun after interruption.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def extract_json(text: str) -> dict[str, Any]:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S | re.I).strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise
        value = json.loads(text[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("Model response is not a JSON object")
    return value


class OllamaClient:
    def __init__(self, base_url: str, model: str, launch_server: bool) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.process: subprocess.Popen[str] | None = None
        if not self.available() and launch_server:
            self.process = subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            for _ in range(60):
                if self.available():
                    break
                time.sleep(1)
        if not self.available():
            raise RuntimeError(f"Ollama is not reachable at {self.base_url}")

    def available(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.base_url}/api/tags", timeout=2) as response:
                return response.status == 200
        except Exception:
            return False

    def close(self) -> None:
        if self.process is not None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()

    def json(self, system: str, prompt: str, validator, retries: int = 4) -> dict[str, Any]:
        last_error: Exception | None = None
        feedback = ""
        for attempt in range(1, retries + 1):
            body = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt + feedback},
                ],
                "temperature": 0.1,
                "response_format": {"type": "json_object"},
                "stream": False,
            }
            request = urllib.request.Request(
                f"{self.base_url}/v1/chat/completions",
                data=json.dumps(body).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=900) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                content = payload["choices"][0]["message"]["content"]
                value = extract_json(content)
                validator(value)
                return value
            except Exception as exc:
                last_error = exc
                feedback = f"\n\nPrevious response failed validation: {exc}. Return one valid JSON object only. Attempt {attempt + 1}."
        raise RuntimeError(f"Model failed after {retries} attempts: {last_error}")


def pipeline(python: Path, script: Path, *args: str) -> dict[str, Any]:
    result = subprocess.run([str(python), str(script), *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip())
    return json.loads(result.stdout)


def exact_items(value: dict[str, Any], expected: set[str], target_required: bool) -> None:
    items = value.get("items")
    if not isinstance(items, list):
        raise ValueError("missing items array")
    received = {item.get("id") for item in items if isinstance(item, dict)}
    if received != expected:
        raise ValueError(f"IDs mismatch; missing={sorted(expected-received)}, extra={sorted(received-expected)}")
    if target_required:
        for item in items:
            if not isinstance(item.get("target"), str) or not item["target"].strip():
                raise ValueError(f"empty target for {item.get('id')}")


def relevant_glossary(terms: list[dict[str, Any]], items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    text = "\n".join(str(item.get("text", "")) for item in items).casefold()
    matches = [term for term in terms if str(term.get("source", "")).casefold() in text or str(term.get("target", "")).casefold() in text]
    seen = {(str(term.get("source", "")).casefold(), str(term.get("target", "")).casefold()) for term in matches}
    for term in terms:
        key = (str(term.get("source", "")).casefold(), str(term.get("target", "")).casefold())
        if key not in seen and len(matches) < 60:
            matches.append(term)
            seen.add(key)
    return matches


def analysis_phase(client: OllamaClient, python: Path, script: Path, work: Path) -> None:
    system = "You are a senior Chinese-English terminology analyst for shipboard military and maritime equipment test specifications. Return strict JSON only."
    count = 0
    while True:
        batch = pipeline(python, script, "next-batch", "--work-dir", str(work), "--phase", "analysis", "--limit", "28", "--chars", "12000")
        if batch["complete"]:
            break
        items = batch["items"]
        prompt = (
            "Read every source unit below. Identify recurring or high-risk professional terms, equipment names, test terminology, abbreviations, and titles. "
            "For Chinese sources give professional English; for English sources give professional Simplified Chinese. Do not translate the document yet. "
            "Return {\"terms\":[{\"source\":...,\"target\":...,\"direction\":...,\"domain\":...,\"definition\":...,\"context_unit_ids\":[...],\"confidence\":\"high|medium|low\",\"notes\":...}]} .\n\n"
            + json.dumps(items, ensure_ascii=False)
        )
        response = client.json(system, prompt, lambda value: isinstance(value.get("terms", []), list) or (_ for _ in ()).throw(ValueError("terms must be an array")))
        response_path = work / "runner-analysis-response.json"
        save_json(response_path, response)
        pipeline(python, script, "ingest", "--work-dir", str(work), "--phase", "analysis", "--response", str(response_path))
        count += len(items)
        print(f"analysis {count} units", flush=True)
    state = load_json(work / "state.json")
    glossary_path = work / "runner-glossary.json"
    save_json(glossary_path, {"terms": state.get("terms", [])})
    pipeline(python, script, "lock-glossary", "--work-dir", str(work), "--file", str(glossary_path))
    print(f"glossary locked: {len(load_json(work / 'state.json').get('terms', []))} terms", flush=True)


def translation_phase(client: OllamaClient, python: Path, script: Path, work: Path) -> None:
    system = "You are a precise senior Chinese-English translator for shipboard military and maritime equipment test specifications. Return strict JSON only, with no explanation."
    count = len(load_json(work / "state.json").get("translations", {}))
    while True:
        batch = pipeline(python, script, "next-batch", "--work-dir", str(work), "--phase", "translation", "--limit", "24", "--chars", "14000")
        if batch["complete"]:
            break
        items = batch["items"]
        expected = {item["id"] for item in items}
        glossary = relevant_glossary(load_json(work / "state.json").get("terms", []), items)
        prompt = (
            "Translate every item according to its direction. Return exactly one item per ID as "
            "{\"items\":[{\"id\":...,\"source_hash\":...,\"target\":...}]}. "
            "Keep the source out of target; output only the translation. Preserve numbers, units, equipment identifiers, standards, punctuation meaning, and test procedure logic. "
            "Use concise formal engineering English or Mainland Chinese. Paragraphs already containing substantive Chinese and English are marked non-translatable by the pipeline and must not be duplicated.\n\n"
            f"GLOSSARY:\n{json.dumps(glossary, ensure_ascii=False)}\n\nITEMS:\n{json.dumps(items, ensure_ascii=False)}"
        )
        response = client.json(system, prompt, lambda value: exact_items(value, expected, True))
        by_id = {item["id"]: item for item in response["items"]}
        response["items"] = [
            {"id": item["id"], "source_hash": item["source_hash"], "target": str(by_id[item["id"]]["target"]).strip()}
            for item in items
        ]
        response_path = work / "runner-translation-response.json"
        save_json(response_path, response)
        pipeline(python, script, "ingest", "--work-dir", str(work), "--phase", "translation", "--response", str(response_path))
        count += len(items)
        print(f"translated {count} units", flush=True)


def review_phase(client: OllamaClient, python: Path, script: Path, work: Path) -> None:
    system = "You are a conservative bilingual QA editor for naval equipment test specifications. Return strict JSON only."
    count = len(load_json(work / "state.json").get("review_done", []))
    while True:
        batch = pipeline(python, script, "next-batch", "--work-dir", str(work), "--phase", "review", "--limit", "24", "--chars", "14000")
        if batch["complete"]:
            break
        state = load_json(work / "state.json")
        items = []
        for item in batch["items"]:
            item = dict(item)
            item["target"] = state.get("review_corrections", {}).get(item["id"], state["translations"][item["id"]])
            items.append(item)
        expected = {item["id"] for item in items}
        glossary = relevant_glossary(state.get("terms", []), items)
        prompt = (
            "Review every source/target pair for omission, wrong meaning, inverted negation, terminology inconsistency, names, numbers, units, and unsupported additions. "
            "Return exactly one record per ID: {\"items\":[{\"id\":...,\"status\":\"ok\"}]} or status \"replace\" with corrected \"target\" and short \"issues\" array. "
            "Do not rewrite acceptable translations merely for style.\n\n"
            f"GLOSSARY:\n{json.dumps(glossary, ensure_ascii=False)}\n\nPAIRS:\n{json.dumps(items, ensure_ascii=False)}"
        )

        def validate_review(value: dict[str, Any]) -> None:
            exact_items(value, expected, False)
            for result in value["items"]:
                status = result.get("status", "ok")
                if status not in {"ok", "replace"}:
                    raise ValueError(f"invalid review status {status}")
                if status == "replace" and (not isinstance(result.get("target"), str) or not result["target"].strip()):
                    raise ValueError(f"replacement missing for {result.get('id')}")

        response = client.json(system, prompt, validate_review)
        response_path = work / "runner-review-response.json"
        save_json(response_path, response)
        pipeline(python, script, "ingest", "--work-dir", str(work), "--phase", "review", "--response", str(response_path))
        count += len(items)
        print(f"reviewed {count} units", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input")
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--model", default="qwen3.6:latest")
    parser.add_argument("--base-url", default=os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434"))
    parser.add_argument("--launch-server", action="store_true")
    args = parser.parse_args()

    work = Path(args.work_dir).expanduser().resolve()
    output = Path(args.output_dir).expanduser().resolve()
    input_path = Path(args.input).expanduser().resolve()
    script = Path(__file__).with_name("document_pipeline.py")
    python = Path(sys.executable)
    work.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    if not (work / "manifest.json").exists():
        pipeline(python, script, "prepare", str(input_path), "--work-dir", str(work))

    client = OllamaClient(args.base_url, args.model, args.launch_server)
    try:
        state = load_json(work / "state.json")
        if not state.get("glossary_locked"):
            analysis_phase(client, python, script, work)
        state = load_json(work / "state.json")
        manifest = load_json(work / "manifest.json")
        total = manifest["translatable_count"]
        if len(state.get("translations", {})) < total:
            translation_phase(client, python, script, work)
        state = load_json(work / "state.json")
        if len(state.get("review_done", [])) < total:
            review_phase(client, python, script, work)
        result = pipeline(python, script, "finalize", "--work-dir", str(work), "--output-dir", str(output))
        pipeline(python, script, "validate", "--work-dir", str(work))
        print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
