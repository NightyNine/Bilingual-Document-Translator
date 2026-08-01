#!/usr/bin/env python3
"""Small successful local-runner stand-in for background job tests."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--provider")
    parser.add_argument("--model")
    parser.add_argument("--batch-size")
    parser.add_argument("--batch-chars")
    parser.add_argument("--base-url")
    parser.add_argument("--launch-server", action="store_true")
    parser.add_argument("--pdf", action="store_true")
    args = parser.parse_args()

    source = Path(args.input)
    work = Path(args.work_dir)
    output = Path(args.output_dir) / source.stem
    work.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    (work / "manifest.json").write_text(
        json.dumps({"translatable_count": 1}), encoding="utf-8"
    )
    (work / "state.json").write_text(
        json.dumps(
            {
                "analysis_done": ["unit-1"],
                "translations": {"unit-1": "译文"},
                "review_done": ["unit-1"],
            }
        ),
        encoding="utf-8",
    )
    print("fake translation started", flush=True)
    time.sleep(0.5)
    suffix = source.suffix.lower() if source.suffix.lower() in {".xlsx", ".xlsm"} else ".docx"
    (output / f"{source.stem}.bilingual{suffix}").write_bytes(b"test")
    (output / f"{source.stem}.qa.json").write_text(
        json.dumps({"passed": True}), encoding="utf-8"
    )
    print("fake translation completed", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
