#!/usr/bin/env python3
"""Deterministic one-command entrypoint for Hermes file translation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


SUPPORTED = {".doc", ".docx", ".pdf", ".xlsx", ".xlsm"}


def safe_stem(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._-")
    return cleaned or "document"


def default_output_root(input_path: Path) -> Path:
    cwd_output = Path.cwd() / "Output Files"
    if cwd_output.is_dir():
        return cwd_output.resolve()
    if input_path.parent.name.casefold() == "original files":
        return (input_path.parent.parent / "Output Files").resolve()
    return (input_path.parent / "Output Files").resolve()


def default_work_dir(input_path: Path) -> Path:
    identity = hashlib.sha256(str(input_path).encode("utf-8")).hexdigest()[:10]
    return Path("/private/tmp") / f"{safe_stem(input_path.stem)}_{identity}_bilingual_work"


def normalize_input(input_path: Path, work_dir: Path) -> Path:
    suffix = input_path.suffix.lower()
    if suffix != ".doc":
        return input_path
    if sys.platform != "darwin" or shutil.which("textutil") is None:
        raise RuntimeError(
            "Legacy .doc input requires macOS textutil or conversion to .docx first."
        )
    converted_dir = work_dir / "converted-input"
    converted_dir.mkdir(parents=True, exist_ok=True)
    converted = converted_dir / f"{input_path.stem}.docx"
    if converted.is_file() and converted.stat().st_mtime >= input_path.stat().st_mtime:
        return converted
    result = subprocess.run(
        ["textutil", "-convert", "docx", "-output", str(converted), str(input_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not converted.is_file():
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"Failed to convert legacy .doc input: {detail}")
    return converted


def background_command(args: argparse.Namespace, normalized_input: Path) -> list[str]:
    script = Path(__file__).with_name("background_job.py").resolve()
    command = [
        sys.executable,
        str(script),
        "start",
        str(normalized_input),
        "--work-dir",
        str(args.work_dir),
        "--output-dir",
        str(args.output_dir),
        "--provider",
        args.provider,
        "--model",
        args.model,
        "--batch-size",
        str(args.batch_size),
        "--batch-chars",
        str(args.batch_chars),
    ]
    if args.base_url:
        command.extend(["--base-url", args.base_url])
    if args.skip_excel_rows:
        command.extend(["--skip-excel-rows", args.skip_excel_rows])
    if args.provider == "ollama" and not args.no_launch_server:
        command.append("--launch-server")
    if args.pdf:
        command.append("--pdf")
    if args.runner_python:
        command.extend(["--runner-python", args.runner_python])
    if args.runner_script:
        command.extend(["--runner-script", args.runner_script])
    return command


def run_json(command: list[str]) -> dict[str, Any]:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    output = result.stdout.strip()
    if output:
        print(output, flush=True)
    if result.returncode != 0:
        if result.stderr.strip():
            print(result.stderr.strip(), file=sys.stderr, flush=True)
        raise RuntimeError(f"Command failed with exit code {result.returncode}")
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return {}


def translate(args: argparse.Namespace) -> int:
    normalized = normalize_input(args.input, args.work_dir)
    started = run_json(background_command(args, normalized))
    if started.get("status") == "completed":
        return 0
    wait_script = Path(__file__).with_name("background_job.py").resolve()
    return subprocess.call(
        [
            sys.executable,
            str(wait_script),
            "wait",
            "--work-dir",
            str(args.work_dir),
            "--poll-interval",
            str(args.poll_interval),
        ]
    )


def show_status(args: argparse.Namespace) -> int:
    normalized = normalize_input(args.input, args.work_dir)
    job_file = args.work_dir / "background-job.json"
    if not job_file.is_file():
        print(
            json.dumps(
                {
                    "ok": False,
                    "status": "not-found",
                    "input": str(normalized),
                    "work_dir": str(args.work_dir),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2
    script = Path(__file__).with_name("background_job.py").resolve()
    return subprocess.call(
        [sys.executable, str(script), "status", "--work-dir", str(args.work_dir)]
    )


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    subparsers = root.add_subparsers(dest="action", required=True)
    for action in ("translate", "status"):
        sub = subparsers.add_parser(action)
        sub.add_argument("input", type=Path)
        sub.add_argument("--output-dir", type=Path)
        sub.add_argument("--work-dir", type=Path)
        sub.add_argument("--provider", choices=("ollama", "lmstudio"), default="ollama")
        sub.add_argument("--model", default="qwen3.6:latest")
        sub.add_argument("--base-url")
        sub.add_argument("--batch-size", type=int, default=80)
        sub.add_argument("--batch-chars", type=int, default=30000)
        sub.add_argument("--skip-excel-rows")
        sub.add_argument("--poll-interval", type=float, default=15.0)
        sub.add_argument("--no-launch-server", action="store_true")
        sub.add_argument("--pdf", action="store_true")
        sub.add_argument("--runner-python", help=argparse.SUPPRESS)
        sub.add_argument("--runner-script", help=argparse.SUPPRESS)
        sub.set_defaults(handler=translate if action == "translate" else show_status)
    return root


def main() -> int:
    args = parser().parse_args()
    args.input = args.input.expanduser().resolve()
    if not args.input.is_file():
        raise FileNotFoundError(f"Input file does not exist: {args.input}")
    if args.input.suffix.lower() not in SUPPORTED:
        raise ValueError(f"Unsupported input type: {args.input.suffix}")
    args.output_dir = (
        args.output_dir.expanduser().resolve()
        if args.output_dir
        else default_output_root(args.input)
    )
    args.work_dir = (
        args.work_dir.expanduser().resolve()
        if args.work_dir
        else default_work_dir(args.input)
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.work_dir.mkdir(parents=True, exist_ok=True)
    try:
        return int(args.handler(args))
    except Exception as exc:
        print(
            json.dumps(
                {"ok": False, "status": "error", "error": f"{type(exc).__name__}: {exc}"},
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
