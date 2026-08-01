#!/usr/bin/env python3
"""Launch and monitor a durable local bilingual translation job.

The worker is detached from the calling agent process, so a short tool timeout,
chat turn ending, UI disconnect, or Hermes gateway restart does not terminate
the translation. The underlying local runner remains checkpointed.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


JOB_FILE_NAME = "background-job.json"
LOG_FILE_NAME = "background-job.log"
ACTIVE_STATES = {"starting", "running"}
TERMINAL_STATES = {"completed", "failed", "interrupted"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def save_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def output_paths(input_path: Path, output_root: Path) -> tuple[Path, Path]:
    stem = input_path.stem
    suffix = input_path.suffix.lower()
    if suffix in {".xlsx", ".xlsm"}:
        bilingual_suffix = suffix
    else:
        bilingual_suffix = ".docx"
    folder = output_root / stem
    return (
        folder / f"{stem}.bilingual{bilingual_suffix}",
        folder / f"{stem}.qa.json",
    )


def process_matches(pid: int | None, job_file: Path) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except (OSError, ProcessLookupError):
        return False
    if os.name == "nt":
        return True
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except Exception:
        return True
    command = result.stdout.strip()
    return result.returncode == 0 and (
        "background_job.py" in command or str(job_file) in command
    )


def progress(work_dir: Path) -> dict[str, int | None]:
    manifest_path = work_dir / "manifest.json"
    state_path = work_dir / "state.json"
    manifest: dict[str, Any] = {}
    state: dict[str, Any] = {}
    try:
        if manifest_path.is_file():
            manifest = load_json(manifest_path)
        if state_path.is_file():
            state = load_json(state_path)
    except Exception:
        pass
    return {
        "total": manifest.get("translatable_count"),
        "analysis": len(state.get("analysis_done", [])),
        "translations": len(state.get("translations", {})),
        "reviews": len(state.get("review_done", [])),
    }


def tail(path: Path, lines: int = 12) -> list[str]:
    if not path.is_file():
        return []
    try:
        content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return content[-lines:]


def inspect_job(job_file: Path, persist: bool = True) -> dict[str, Any]:
    job = load_json(job_file)
    work_dir = Path(job["work_dir"])
    input_path = Path(job["input"])
    output_root = Path(job["output_dir"])
    primary_output, qa_path = output_paths(input_path, output_root)
    qa_passed = False
    if qa_path.is_file():
        try:
            qa_passed = bool(load_json(qa_path).get("passed"))
        except Exception:
            qa_passed = False

    changed = False
    status = str(job.get("status", "unknown"))
    alive = process_matches(job.get("worker_pid"), job_file)
    if primary_output.is_file() and qa_passed and status != "completed":
        job["status"] = "completed"
        job.setdefault("completed_at", utc_now())
        changed = True
    elif status in ACTIVE_STATES and not alive:
        job["status"] = "interrupted"
        job["interrupted_at"] = utc_now()
        changed = True
    if changed and persist:
        save_json(job_file, job)

    return {
        "ok": True,
        "status": job.get("status", status),
        "job_file": str(job_file),
        "worker_pid": job.get("worker_pid"),
        "runner_pid": job.get("runner_pid"),
        "process_alive": alive,
        "progress": progress(work_dir),
        "primary_output": str(primary_output),
        "output_exists": primary_output.is_file(),
        "qa_path": str(qa_path),
        "qa_passed": qa_passed,
        "log_path": job.get("log_path"),
        "log_tail": tail(Path(job["log_path"])),
        "exit_code": job.get("exit_code"),
        "started_at": job.get("started_at"),
        "completed_at": job.get("completed_at"),
    }


def detached_options() -> dict[str, Any]:
    options: dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if os.name == "nt":
        options["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        )
    else:
        options["start_new_session"] = True
    return options


def launch_worker(job_file: Path) -> int:
    worker = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "_worker", str(job_file)],
        cwd=str(Path(__file__).resolve().parent),
        **detached_options(),
    )
    job = load_json(job_file)
    job["worker_pid"] = worker.pid
    job["status"] = "running"
    save_json(job_file, job)
    return worker.pid


def runner_python(override: str | None) -> Path:
    if override:
        return Path(override).expanduser().resolve()
    skill_dir = Path(__file__).resolve().parents[1]
    candidate = (
        skill_dir / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    )
    return candidate if candidate.is_file() else Path(sys.executable).resolve()


def command_for(args: argparse.Namespace) -> list[str]:
    runner = (
        Path(args.runner_script).expanduser().resolve()
        if args.runner_script
        else Path(__file__).with_name("local_runner.py").resolve()
    )
    command = [
        str(runner_python(args.runner_python)),
        str(runner),
        str(Path(args.input).expanduser().resolve()),
        "--work-dir",
        str(Path(args.work_dir).expanduser().resolve()),
        "--output-dir",
        str(Path(args.output_dir).expanduser().resolve()),
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
    if args.launch_server:
        command.append("--launch-server")
    if args.pdf:
        command.append("--pdf")
    return command


def start(args: argparse.Namespace) -> int:
    input_path = Path(args.input).expanduser().resolve()
    work_dir = Path(args.work_dir).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    if not input_path.is_file():
        raise FileNotFoundError(f"Input file does not exist: {input_path}")
    work_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    job_file = work_dir / JOB_FILE_NAME

    if job_file.is_file():
        current = inspect_job(job_file)
        existing = load_json(job_file)
        same_input = Path(existing.get("input", "")).resolve() == input_path
        if same_input and current["status"] == "running":
            current["launch_status"] = "already-running"
            print(json.dumps(current, ensure_ascii=False, indent=2), flush=True)
            return 0
        if same_input and current["status"] == "completed":
            current["launch_status"] = "already-completed"
            print(json.dumps(current, ensure_ascii=False, indent=2), flush=True)
            return 0

    log_path = work_dir / LOG_FILE_NAME
    job = {
        "version": 1,
        "status": "starting",
        "input": str(input_path),
        "work_dir": str(work_dir),
        "output_dir": str(output_dir),
        "log_path": str(log_path),
        "command": command_for(args),
        "started_at": utc_now(),
        "worker_pid": None,
        "runner_pid": None,
        "exit_code": None,
    }
    save_json(job_file, job)
    worker_pid = launch_worker(job_file)
    result = inspect_job(job_file)
    result["launch_status"] = "started"
    result["worker_pid"] = worker_pid
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    return 0


def resume(args: argparse.Namespace) -> int:
    job_file = Path(args.work_dir).expanduser().resolve() / JOB_FILE_NAME
    if not job_file.is_file():
        raise FileNotFoundError(f"No background job found at {job_file}")
    current = inspect_job(job_file)
    if current["status"] in {"running", "completed"}:
        current["launch_status"] = (
            "already-running" if current["status"] == "running" else "already-completed"
        )
        print(json.dumps(current, ensure_ascii=False, indent=2), flush=True)
        return 0
    job = load_json(job_file)
    job.update(
        {
            "status": "starting",
            "started_at": utc_now(),
            "completed_at": None,
            "interrupted_at": None,
            "exit_code": None,
            "runner_pid": None,
        }
    )
    save_json(job_file, job)
    worker_pid = launch_worker(job_file)
    result = inspect_job(job_file)
    result["launch_status"] = "resumed"
    result["worker_pid"] = worker_pid
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    return 0


def worker(job_file: Path) -> int:
    # The launcher records the detached worker PID immediately after Popen.
    # Wait for that atomic hand-off before the worker begins updating the same
    # job file, preventing an unusually fast child from racing the launcher and
    # losing runner_pid metadata.
    for _ in range(100):
        job = load_json(job_file)
        if job.get("worker_pid") == os.getpid():
            break
        time.sleep(0.02)
    job = load_json(job_file)
    log_path = Path(job["log_path"])
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8", buffering=1) as log:
        log.write(f"[{utc_now()}] background worker started; pid={os.getpid()}\n")
        try:
            process = subprocess.Popen(
                job["command"],
                cwd=str(Path(__file__).resolve().parent),
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                close_fds=True,
                text=True,
            )
            job = load_json(job_file)
            job.update(
                {
                    "status": "running",
                    "worker_pid": os.getpid(),
                    "runner_pid": process.pid,
                }
            )
            save_json(job_file, job)
            return_code = process.wait()
            job = load_json(job_file)
            job["exit_code"] = return_code
            job["completed_at"] = utc_now()
            job["status"] = "completed" if return_code == 0 else "failed"
            save_json(job_file, job)
            log.write(
                f"[{utc_now()}] background worker finished; exit_code={return_code}\n"
            )
            return return_code
        except BaseException as exc:
            job = load_json(job_file)
            job.update(
                {
                    "status": "failed",
                    "exit_code": 1,
                    "completed_at": utc_now(),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            save_json(job_file, job)
            log.write(f"[{utc_now()}] background worker failed: {exc!r}\n")
            return 1


def show_status(args: argparse.Namespace) -> int:
    job_file = Path(args.work_dir).expanduser().resolve() / JOB_FILE_NAME
    if not job_file.is_file():
        print(
            json.dumps(
                {"ok": False, "status": "not-found", "job_file": str(job_file)},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2
    print(json.dumps(inspect_job(job_file), ensure_ascii=False, indent=2), flush=True)
    return 0


def wait_for_job(args: argparse.Namespace) -> int:
    job_file = Path(args.work_dir).expanduser().resolve() / JOB_FILE_NAME
    if not job_file.is_file():
        raise FileNotFoundError(f"No background job found at {job_file}")
    previous: tuple[Any, ...] | None = None
    while True:
        result = inspect_job(job_file)
        marker = (
            result["status"],
            result["progress"]["analysis"],
            result["progress"]["translations"],
            result["progress"]["reviews"],
        )
        if marker != previous:
            print(json.dumps(result, ensure_ascii=False), flush=True)
            previous = marker
        if result["status"] in TERMINAL_STATES:
            return 0 if result["status"] == "completed" else 2
        time.sleep(args.poll_interval)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command_name", required=True)

    start_parser = subparsers.add_parser("start", help="Start or reuse a durable job")
    start_parser.add_argument("input")
    start_parser.add_argument("--work-dir", required=True)
    start_parser.add_argument("--output-dir", required=True)
    start_parser.add_argument("--provider", choices=("ollama", "lmstudio"), default="ollama")
    start_parser.add_argument("--model", default="qwen3.6:latest")
    start_parser.add_argument("--base-url")
    start_parser.add_argument("--batch-size", type=int, default=80)
    start_parser.add_argument("--batch-chars", type=int, default=30000)
    start_parser.add_argument("--launch-server", action="store_true")
    start_parser.add_argument("--pdf", action="store_true")
    start_parser.add_argument("--runner-python", help=argparse.SUPPRESS)
    start_parser.add_argument("--runner-script", help=argparse.SUPPRESS)
    start_parser.set_defaults(handler=start)

    resume_parser = subparsers.add_parser("resume", help="Resume an interrupted job")
    resume_parser.add_argument("--work-dir", required=True)
    resume_parser.set_defaults(handler=resume)

    status_parser = subparsers.add_parser("status", help="Show progress and output status")
    status_parser.add_argument("--work-dir", required=True)
    status_parser.set_defaults(handler=show_status)

    wait_parser = subparsers.add_parser("wait", help="Wait until the durable job exits")
    wait_parser.add_argument("--work-dir", required=True)
    wait_parser.add_argument("--poll-interval", type=float, default=15.0)
    wait_parser.set_defaults(handler=wait_for_job)

    worker_parser = subparsers.add_parser("_worker", help=argparse.SUPPRESS)
    worker_parser.add_argument("job_file", type=Path)
    worker_parser.set_defaults(handler=lambda args: worker(args.job_file.resolve()))
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if getattr(args, "batch_size", 1) < 1:
        parser.error("--batch-size must be at least 1")
    if getattr(args, "batch_chars", 1000) < 1000:
        parser.error("--batch-chars must be at least 1000")
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
            flush=True,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
