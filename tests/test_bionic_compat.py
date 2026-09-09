from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from local_runner import LocalModelClient  # noqa: E402


class MockLMStudioHandler(BaseHTTPRequestHandler):
    authorization = ""
    request_body: dict[str, object] = {}

    def do_GET(self) -> None:
        if self.path not in {"/v1/models", "/api/tags"}:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"object":"list","data":[{"id":"test-model"}]}')

    def do_POST(self) -> None:
        if self.path != "/v1/chat/completions":
            self.send_error(404)
            return
        type(self).authorization = self.headers.get("Authorization", "")
        length = int(self.headers.get("Content-Length", "0"))
        type(self).request_body = json.loads(self.rfile.read(length))
        payload = {
            "choices": [
                {
                    "message": {
                        "content": '{"items":[{"id":"unit-1","target":"译文"}]}'
                    }
                }
            ]
        }
        encoded = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: object) -> None:
        return


class BionicCompatibilityTests(unittest.TestCase):
    def test_lmstudio_openai_compatible_backend(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), MockLMStudioHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            client = LocalModelClient(
                f"http://127.0.0.1:{server.server_port}",
                "test-model",
                False,
                "lmstudio",
                "secret-token",
            )
            response = client.json(
                "Return JSON.",
                "Translate.",
                lambda value: self.assertEqual(value["items"][0]["id"], "unit-1"),
            )
            self.assertEqual(response["items"][0]["target"], "译文")
            self.assertEqual(MockLMStudioHandler.authorization, "Bearer secret-token")
            self.assertEqual(
                MockLMStudioHandler.request_body["model"],
                "test-model",
            )
            self.assertEqual(
                MockLMStudioHandler.request_body["response_format"],
                {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "bilingual_pipeline_response",
                        "schema": {"type": "object"},
                    },
                },
            )
        finally:
            server.shutdown()
            server.server_close()

    def test_bionic_project_install(self) -> None:
        with tempfile.TemporaryDirectory() as project:
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/install_skill.py"),
                    "--agent",
                    "bionic",
                    "--scope",
                    "project",
                    "--project-dir",
                    project,
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            payload = json.loads(result.stdout)
            self.assertEqual(payload["results"][0]["status"], "installed")
            self.assertEqual(
                payload["results"][0]["entrypoint_status"],
                "installed",
            )
            project_path = Path(project)
            self.assertTrue(
                (
                    project_path
                    / ".bionic/skills/bilingual-document-translator/SKILL.md"
                ).is_file()
            )
            self.assertEqual(
                (
                    project_path
                    / ".bionic/skills/bilingual-document-translator/VERSION"
                ).read_text(encoding="utf-8").strip(),
                "1.1.0",
            )
            self.assertTrue(
                (
                    project_path
                    / ".bionic/skills/bilingual-document-translator/scripts/background_job.py"
                ).is_file()
            )
            self.assertTrue(
                (
                    project_path / ".bionic/bilingual-document-translator.md"
                ).is_file()
            )

    def test_ollama_backend_remains_compatible(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), MockLMStudioHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            client = LocalModelClient(
                f"http://127.0.0.1:{server.server_port}",
                "test-model",
                False,
                "ollama",
                None,
            )
            client.json("Return JSON.", "Translate.", lambda value: None)
            self.assertEqual(
                MockLMStudioHandler.request_body["response_format"],
                {"type": "json_object"},
            )
        finally:
            server.shutdown()
            server.server_close()

    def test_bionic_user_install_is_rejected_with_remedy(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/install_skill.py"),
                "--agent",
                "bionic",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("--scope project", result.stderr)


if __name__ == "__main__":
    unittest.main()
