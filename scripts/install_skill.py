#!/usr/bin/env python3
"""Install this portable Agent Skills bundle for one or more agent hosts."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import uuid
from pathlib import Path


SKILL_ID = "bilingual-document-translator"
COPY_ENTRIES = ("SKILL.md", "agents", "references", "scripts", "LICENSE")
USER_TARGETS = {
    "hermes": Path(".hermes/skills/productivity"),
    "codex": Path(".codex/skills"),
    "claude": Path(".claude/skills"),
    "copilot": Path(".copilot/skills"),
    "cursor": Path(".cursor/skills"),
    "opencode": Path(".config/opencode/skills"),
    "agents": Path(".agents/skills"),
}
PROJECT_TARGETS = {
    "hermes": Path(".hermes/skills/productivity"),
    "codex": Path(".agents/skills"),
    "claude": Path(".claude/skills"),
    "copilot": Path(".github/skills"),
    "cursor": Path(".cursor/skills"),
    "opencode": Path(".opencode/skills"),
    "agents": Path(".agents/skills"),
    "bionic": Path(".bionic/skills"),
}
BIONIC_ENTRY_SOURCE = Path("agents/bionic.md")
BIONIC_ENTRY_TARGET = Path(".bionic/bilingual-document-translator.md")


def ignore_copy(path: str, names: list[str]) -> set[str]:
    ignored = {
        name
        for name in names
        if name in {".git", ".venv", "__pycache__", ".DS_Store"}
        or name.endswith((".pyc", ".pyo"))
    }
    return ignored


def copy_bundle(source: Path, target: Path, force: bool, dry_run: bool) -> str:
    if target.resolve() == source.resolve():
        return "source"
    if target.exists() and not force:
        return "skipped-existing"
    if dry_run:
        return "would-update" if target.exists() else "would-install"

    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        for entry in COPY_ENTRIES:
            item = source / entry
            if not item.exists():
                continue
            destination = target / entry
            if item.is_dir():
                shutil.copytree(item, destination, dirs_exist_ok=True, ignore=ignore_copy)
            else:
                shutil.copy2(item, destination)
        return "updated"

    staging = target.parent / f".{SKILL_ID}.install-{uuid.uuid4().hex}"
    try:
        staging.mkdir()
        for entry in COPY_ENTRIES:
            item = source / entry
            if not item.exists():
                continue
            destination = staging / entry
            if item.is_dir():
                shutil.copytree(item, destination, ignore=ignore_copy)
            else:
                shutil.copy2(item, destination)
        staging.rename(target)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return "installed"


def copy_file(source: Path, target: Path, force: bool, dry_run: bool) -> str:
    existed = target.exists()
    if existed and not force:
        return "skipped-existing"
    if dry_run:
        return "would-update" if existed else "would-install"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return "updated" if existed else "installed"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Install Bilingual-Document-Translator for popular agent hosts."
    )
    parser.add_argument(
        "--agent",
        action="append",
        choices=[*dict.fromkeys([*USER_TARGETS, *PROJECT_TARGETS]), "all"],
        default=[],
        help="Host to install for; repeatable. Bionic is project-scope only. Defaults to all.",
    )
    parser.add_argument(
        "--scope",
        choices=("user", "project"),
        default="user",
        help="Install under the user home or a project directory.",
    )
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=Path.cwd(),
        help="Project root used with --scope project.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Update known bundle files in an existing installation.",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    selected = args.agent or ["all"]
    target_map = USER_TARGETS if args.scope == "user" else PROJECT_TARGETS
    if "all" in selected:
        selected = list(target_map)
    selected = list(dict.fromkeys(selected))
    unsupported = [agent for agent in selected if agent not in target_map]
    if unsupported:
        parser.error(
            "Bionic does not publish a user-level Skill directory. "
            "Install it into a Bionic Code Project with "
            "`--agent bionic --scope project --project-dir /absolute/project`."
        )
    source = Path(__file__).resolve().parents[1]
    base = Path.home() if args.scope == "user" else args.project_dir.expanduser().resolve()

    results = []
    seen_targets: set[Path] = set()
    for agent in selected:
        target = (base / target_map[agent] / SKILL_ID).resolve()
        if target in seen_targets:
            results.append({"agent": agent, "target": str(target), "status": "shared-target"})
            continue
        seen_targets.add(target)
        status = copy_bundle(source, target, args.force, args.dry_run)
        result = {"agent": agent, "target": str(target), "status": status}
        if agent == "bionic":
            entry_target = base / BIONIC_ENTRY_TARGET
            entry_status = copy_file(
                source / BIONIC_ENTRY_SOURCE,
                entry_target,
                args.force,
                args.dry_run,
            )
            result["entrypoint"] = str(entry_target)
            result["entrypoint_status"] = entry_status
        results.append(result)

    print(json.dumps({"skill": SKILL_ID, "scope": args.scope, "results": results}, indent=2))
    failed = any(
        result["status"] == "skipped-existing"
        or result.get("entrypoint_status") == "skipped-existing"
        for result in results
    )
    if failed:
        print("Existing installs were left untouched; rerun with --force to update them.", file=sys.stderr)
    return 2 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
