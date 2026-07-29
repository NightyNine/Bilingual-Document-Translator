#!/usr/bin/env python3
"""Run the entire bilingual pipeline against Ollama or LM Studio.

This companion avoids hundreds of agent tool turns for long documents while
keeping all semantic work on the user's local model server. It is fully
checkpointed through document_pipeline.py and can be rerun after interruption.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


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


class LocalModelClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        launch_server: bool,
        provider: str,
        api_key: str | None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.provider = provider
        self.api_key = api_key
        self.process: subprocess.Popen[str] | None = None
        if not self.available() and launch_server:
            self.launch()
            for _ in range(60):
                if self.available():
                    break
                time.sleep(1)
        if not self.available():
            hint = (
                "Run `lms server start` or enable the server in LM Studio's Developer tab."
                if self.provider == "lmstudio"
                else "Run `ollama serve` or pass --launch-server."
            )
            raise RuntimeError(
                f"{self.provider} is not reachable at {self.base_url}. {hint}"
            )

    def headers(self, *, json_content: bool = False) -> dict[str, str]:
        headers: dict[str, str] = {}
        if json_content:
            headers["Content-Type"] = "application/json"
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def health_url(self) -> str:
        path = "/v1/models" if self.provider == "lmstudio" else "/api/tags"
        return f"{self.base_url}{path}"

    def available(self) -> bool:
        try:
            request = urllib.request.Request(
                self.health_url(),
                headers=self.headers(),
                method="GET",
            )
            with urllib.request.urlopen(request, timeout=2) as response:
                return response.status == 200
        except Exception:
            return False

    def launch(self) -> None:
        if self.provider == "ollama":
            if shutil.which("ollama") is None:
                raise RuntimeError("Cannot launch Ollama: `ollama` is not installed.")
            self.process = subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            return
        if shutil.which("lms") is None:
            raise RuntimeError(
                "Cannot launch LM Studio: `lms` is not installed. "
                "Start the server from LM Studio's Developer tab or install the CLI."
            )
        parsed = urlparse(self.base_url)
        port = parsed.port or 1234
        result = subprocess.run(
            ["lms", "server", "start", "--port", str(port)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Unable to start LM Studio server: "
                f"{(result.stderr or result.stdout).strip()}"
            )

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
            response_format = (
                {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "bilingual_pipeline_response",
                        "schema": {"type": "object"},
                    },
                }
                if self.provider == "lmstudio"
                else {"type": "json_object"}
            )
            body = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt + feedback},
                ],
                "temperature": 0.1,
                "response_format": response_format,
                "stream": False,
            }
            request = urllib.request.Request(
                f"{self.base_url}/v1/chat/completions",
                data=json.dumps(body).encode("utf-8"),
                headers=self.headers(json_content=True),
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
    return [
        {
            "source": term.get("source", ""),
            "target": term.get("target", ""),
            "direction": term.get("direction", "auto"),
        }
        for term in matches
    ]


def analysis_phase(
    client: LocalModelClient,
    python: Path,
    script: Path,
    work: Path,
    batch_size: int,
    batch_chars: int,
) -> None:
    system = "You are a senior Chinese-English terminology analyst. Infer the document domain from the supplied text and return strict JSON only."
    count = 0
    while True:
        batch = pipeline(
            python,
            script,
            "next-batch",
            "--work-dir",
            str(work),
            "--phase",
            "analysis",
            "--limit",
            str(batch_size),
            "--chars",
            str(batch_chars),
        )
        if batch["complete"]:
            break
        items = batch["items"]
        prompt = (
            "Read every source unit below. Identify recurring or high-risk professional terms, domain-specific concepts, names, abbreviations, measurements, and titles. "
            "For Chinese sources give professional English; for English sources give professional Simplified Chinese. Do not translate the document yet. "
            "Return a concise glossary as {\"terms\":[{\"source\":...,\"target\":...,\"direction\":...,\"domain\":...,"
            "\"context_unit_ids\":[...],\"confidence\":\"high|medium|low\",\"notes\":...}]}. "
            "Omit generic words and keep notes empty unless a term is genuinely ambiguous.\n\n"
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


def translation_phase(
    client: LocalModelClient,
    python: Path,
    script: Path,
    work: Path,
    batch_size: int,
    batch_chars: int,
) -> None:
    system = "You are a precise senior Chinese-English translator. Match the document's inferred professional domain and return strict JSON only, with no explanation."
    count = len(load_json(work / "state.json").get("translations", {}))
    while True:
        batch = pipeline(
            python,
            script,
            "next-batch",
            "--work-dir",
            str(work),
            "--phase",
            "translation",
            "--limit",
            str(batch_size),
            "--chars",
            str(batch_chars),
        )
        if batch["complete"]:
            break
        items = batch["items"]
        expected = {item["id"] for item in items}
        glossary = relevant_glossary(load_json(work / "state.json").get("terms", []), items)
        prompt = (
            "Translate every item according to its direction. Return exactly one item per ID as "
            "{\"items\":[{\"id\":...,\"source_hash\":...,\"target\":...}]}. "
            "Keep the source out of target; output only the translation. Preserve names, numbers, dates, units, identifiers, standards, formulas, citations, and procedural logic. "
            "Use professional English or Mainland Chinese appropriate to the document's domain and register. Paragraphs already containing substantive Chinese and English are marked non-translatable by the pipeline and must not be duplicated.\n\n"
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


def review_phase(
    client: LocalModelClient,
    python: Path,
    script: Path,
    work: Path,
    batch_size: int,
    batch_chars: int,
) -> None:
    system = "You are a conservative bilingual QA editor. Match the document's professional domain and return strict JSON only."
    count = len(load_json(work / "state.json").get("review_done", []))
    while True:
        batch = pipeline(
            python,
            script,
            "next-batch",
            "--work-dir",
            str(work),
            "--phase",
            "review",
            "--limit",
            str(batch_size),
            "--chars",
            str(batch_chars),
        )
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
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Output root; results are written to <output-dir>/<source-filename>/",
    )
    parser.add_argument(
        "--provider",
        choices=("ollama", "lmstudio"),
        default="ollama",
        help="Local model server. Defaults to ollama.",
    )
    parser.add_argument("--model", default="qwen3.6:latest")
    parser.add_argument(
        "--base-url",
        help="Server root URL. Defaults to port 11434 for Ollama or 1234 for LM Studio.",
    )
    parser.add_argument(
        "--api-key",
        help="Optional bearer token. Defaults to LM_API_TOKEN for LM Studio.",
    )
    parser.add_argument("--launch-server", action="store_true")
    parser.add_argument("--batch-size", type=int, default=80, help="Units per model call; default 80 for fast local processing")
    parser.add_argument("--batch-chars", type=int, default=30000, help="Maximum source characters per model call")
    parser.add_argument("--pdf", action="store_true", help="Also export PDF; omitted by default for faster DOCX-only output")
    args = parser.parse_args()
    if args.batch_size < 1:
        parser.error("--batch-size must be at least 1")
    if args.batch_chars < 1000:
        parser.error("--batch-chars must be at least 1000")

    work = Path(args.work_dir).expanduser().resolve()
    output = Path(args.output_dir).expanduser().resolve()
    input_path = Path(args.input).expanduser().resolve()
    script = Path(__file__).with_name("document_pipeline.py")
    python = Path(sys.executable)
    default_url = (
        os.environ.get("LM_STUDIO_BASE_URL", "http://127.0.0.1:1234")
        if args.provider == "lmstudio"
        else os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    )
    base_url = args.base_url or default_url
    api_key = args.api_key
    if api_key is None and args.provider == "lmstudio":
        api_key = os.environ.get("LM_API_TOKEN")
    work.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    if not (work / "manifest.json").exists():
        pipeline(python, script, "prepare", str(input_path), "--work-dir", str(work))

    client = LocalModelClient(
        base_url,
        args.model,
        args.launch_server,
        args.provider,
        api_key,
    )
    try:
        state = load_json(work / "state.json")
        if not state.get("glossary_locked"):
            analysis_phase(client, python, script, work, args.batch_size, args.batch_chars)
        state = load_json(work / "state.json")
        manifest = load_json(work / "manifest.json")
        total = manifest["translatable_count"]
        if len(state.get("translations", {})) < total:
            translation_phase(client, python, script, work, args.batch_size, args.batch_chars)
        state = load_json(work / "state.json")
        if len(state.get("review_done", [])) < total:
            review_phase(client, python, script, work, args.batch_size, args.batch_chars)
        finalize_args = ["finalize", "--work-dir", str(work), "--output-dir", str(output)]
        if args.pdf:
            finalize_args.append("--pdf")
        result = pipeline(python, script, *finalize_args)
        pipeline(python, script, "validate", "--work-dir", str(work))
        print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
