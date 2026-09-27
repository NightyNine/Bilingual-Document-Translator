"""Resolve the current Hermes profile without storing credentials in job files."""

from pathlib import Path
import json
import os
import subprocess
import sys


def resolve_agent_model(model=""):
    root = Path(os.environ.get("HERMES_AGENT_ROOT", str(Path.home() / ".hermes/hermes-agent")))
    python = root / "venv/bin/python"
    if not python.is_file():
        raise RuntimeError("Hermes Python runtime is unavailable; cannot inherit its model. Set HERMES_AGENT_ROOT.")
    result = subprocess.run(
        [str(python), str(Path(__file__).resolve()), str(root), model or ""],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode:
        raise RuntimeError("Cannot resolve the Hermes default model; no fallback model was selected.")
    return json.loads(result.stdout)


def main():
    sys.path.insert(0, sys.argv[1])
    from hermes_cli.config import load_config
    from hermes_cli.runtime_provider import resolve_runtime_provider

    config = load_config()
    model_config = config.get("model", {})
    if not isinstance(model_config, dict):
        raise RuntimeError("Hermes model configuration must specify provider and default model.")
    model = sys.argv[2] or model_config.get("default")
    provider = model_config.get("provider")
    if not model or not provider:
        raise RuntimeError("Hermes default model/provider is not configured.")
    runtime = resolve_runtime_provider(requested=provider, target_model=model)
    if runtime.get("api_mode") != "chat_completions":
        raise RuntimeError("The translator currently requires a chat_completions model endpoint; no fallback is allowed.")
    url = str(runtime.get("base_url") or "").rstrip("/")
    if not url:
        raise RuntimeError("Hermes model endpoint is empty.")
    overrides = runtime.get("request_overrides") or {}
    print(
        json.dumps(
            {
                "model": runtime.get("model") or model,
                "base_url": url,
                "api_key": runtime.get("api_key"),
                "extra_body": overrides.get("extra_body") or {},
                "extra_headers": overrides.get("extra_headers") or {},
            }
        )
    )


if __name__ == "__main__":
    main()
