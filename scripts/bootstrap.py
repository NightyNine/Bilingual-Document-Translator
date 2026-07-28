#!/usr/bin/env python3
"""Install the skill's optional document-processing runtime in a local venv."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--skill-dir",
        default=os.environ.get("BILINGUAL_TRANSLATOR_SKILL_DIR")
        or os.environ.get("HERMES_SKILL_DIR"),
    )
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args()
    skill_dir = Path(args.skill_dir).expanduser().resolve() if args.skill_dir else Path(__file__).resolve().parents[1]
    venv = skill_dir / ".venv"
    if not (venv / "bin" / "python").exists():
        subprocess.run([args.python, "-m", "venv", str(venv)], check=True)
    pip = venv / "bin" / "pip"
    subprocess.run([str(pip), "install", "-r", str(skill_dir / "scripts" / "requirements.txt")], check=True)
    checks = {"python": str(venv / "bin" / "python"), "soffice": shutil.which("soffice") or shutil.which("libreoffice"), "tesseract": shutil.which("tesseract")}
    print(checks)
    if not checks["soffice"]:
        print("Warning: LibreOffice/soffice is not available; PDF export will be skipped.", file=sys.stderr)
    if not checks["tesseract"]:
        print("Warning: Tesseract is not available; scanned PDF OCR will be unavailable.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
