from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
JOB_SCRIPT = ROOT / "scripts/background_job.py"
FAKE_RUNNER = ROOT / "tests/fixtures/fake_local_runner.py"


class BackgroundJobTests(unittest.TestCase):
    def test_skill_enforces_hermes_durable_execution(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        description = skill.split("description: ", 1)[1].splitlines()[0]
        self.assertLessEqual(len(description), 60)
        self.assertIn("never run", skill)
        self.assertIn("inside `execute_code`", skill)
        self.assertIn("background_job.py\" start", skill)
        self.assertIn("background=true", skill)
        self.assertIn("notify_on_complete=true", skill)
        self.assertIn("background_job.py\" resume", skill)

    def test_detached_job_completes_and_reports_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "offline test.xlsx"
            source.write_bytes(b"test")
            work = root / "work"
            output = root / "Output Files"

            started = subprocess.run(
                [
                    sys.executable,
                    str(JOB_SCRIPT),
                    "start",
                    str(source),
                    "--work-dir",
                    str(work),
                    "--output-dir",
                    str(output),
                    "--runner-python",
                    sys.executable,
                    "--runner-script",
                    str(FAKE_RUNNER),
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=5,
            )
            start_payload = json.loads(started.stdout)
            self.assertEqual(start_payload["launch_status"], "started")
            self.assertIn(start_payload["status"], {"running", "completed"})

            waited = subprocess.run(
                [
                    sys.executable,
                    str(JOB_SCRIPT),
                    "wait",
                    "--work-dir",
                    str(work),
                    "--poll-interval",
                    "0.05",
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            )
            final_payload = json.loads(waited.stdout.strip().splitlines()[-1])
            self.assertEqual(final_payload["status"], "completed")
            self.assertIsInstance(final_payload["worker_pid"], int)
            self.assertIsInstance(final_payload["runner_pid"], int)
            self.assertTrue(final_payload["output_exists"])
            self.assertTrue(final_payload["qa_passed"])
            self.assertEqual(final_payload["progress"]["translations"], 1)
            self.assertIn(
                "fake translation completed",
                (work / "background-job.log").read_text(encoding="utf-8"),
            )

            status = subprocess.run(
                [
                    sys.executable,
                    str(JOB_SCRIPT),
                    "status",
                    "--work-dir",
                    str(work),
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=5,
            )
            status_payload = json.loads(status.stdout)
            self.assertEqual(status_payload["status"], "completed")

    def test_second_start_reuses_completed_job(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "reuse.docx"
            source.write_bytes(b"test")
            work = root / "work"
            output = root / "output"
            command = [
                sys.executable,
                str(JOB_SCRIPT),
                "start",
                str(source),
                "--work-dir",
                str(work),
                "--output-dir",
                str(output),
                "--runner-python",
                sys.executable,
                "--runner-script",
                str(FAKE_RUNNER),
            ]
            subprocess.run(command, capture_output=True, text=True, check=True, timeout=5)
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                result = subprocess.run(
                    [
                        sys.executable,
                        str(JOB_SCRIPT),
                        "status",
                        "--work-dir",
                        str(work),
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=5,
                )
                if json.loads(result.stdout)["status"] == "completed":
                    break
                time.sleep(0.05)
            else:
                self.fail("background job did not complete")

            repeated = subprocess.run(
                command, capture_output=True, text=True, check=True, timeout=5
            )
            self.assertEqual(
                json.loads(repeated.stdout)["launch_status"], "already-completed"
            )


if __name__ == "__main__":
    unittest.main()
