from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "src")
    return subprocess.run(
        [sys.executable, "-m", "panagent", *args],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


class CLITests(unittest.TestCase):
    def test_autodetect_claude_to_codex_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "codex.jsonl"
            report = Path(directory) / "report.json"
            result = run_cli("convert", str(FIXTURES / "claude-code.jsonl"), "--to", "codex", "-o", str(output), "--report", str(report))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("claude-code -> codex", result.stderr)
            records = [json.loads(line) for line in output.read_text().splitlines()]
            self.assertEqual(records[0]["type"], "session_meta")
            loss = json.loads(report.read_text())
            self.assertEqual(loss["content_blocks"]["tool_call"], 1)
            self.assertTrue(loss["warnings"])

    def test_chatgpt_to_claude_defaults_to_context(self) -> None:
        result = run_cli("convert", str(FIXTURES / "chatgpt-share.html"), "--to", "claude-code")
        self.assertEqual(result.returncode, 0, result.stderr)
        records = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(len(records), 1)
        self.assertIn("imported conversation snapshot", records[0]["message"]["content"].lower())
        self.assertIn("(context)", result.stderr)

    def test_claude_export_to_neutral_ir(self) -> None:
        result = run_cli("convert", str(FIXTURES / "claude-share-export.json"), "--to", "ir", "--quiet")
        self.assertEqual(result.returncode, 0, result.stderr)
        conv = json.loads(result.stdout)
        self.assertEqual(conv["schema"], "https://panagent.dev/schema/conversation/v1")
        self.assertEqual(conv["source"]["provider"], "anthropic")

    def test_native_output_accepts_an_explicit_destination_session_id(self) -> None:
        destination = "13a24696-e6c4-4f2e-bf29-4234eac1af21"
        for target in ("claude-code", "codex"):
            with self.subTest(target=target):
                result = run_cli(
                    "convert",
                    str(FIXTURES / "claude-code.jsonl"),
                    "--to",
                    target,
                    "--session-id",
                    destination,
                    "--quiet",
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                records = [json.loads(line) for line in result.stdout.splitlines() if line]
                if target == "claude-code":
                    self.assertTrue(records)
                    self.assertTrue(all(record["sessionId"] == destination for record in records))
                else:
                    self.assertEqual(records[0]["type"], "session_meta")
                    self.assertEqual(records[0]["payload"]["id"], destination)

        invalid = run_cli(
            "convert",
            str(FIXTURES / "claude-code.jsonl"),
            "--to",
            "codex",
            "--session-id",
            "not-a-uuid",
        )
        self.assertEqual(invalid.returncode, 2)
        self.assertIn("session id must be a UUID", invalid.stderr)

    def test_warning_policy_exit_status(self) -> None:
        result = run_cli("convert", str(FIXTURES / "claude-share-export.json"), "--to", "ir", "--fail-on-warning", "--quiet")
        self.assertEqual(result.returncode, 3)
        self.assertTrue(result.stdout.startswith("{"))

    def test_challenge_has_actionable_failure(self) -> None:
        result = run_cli("convert", str(FIXTURES / "claude-challenge.html"), "--to", "ir")
        self.assertEqual(result.returncode, 2)
        self.assertIn("docs/browser-export.md", result.stderr)

    def test_validate(self) -> None:
        result = run_cli("validate", str(FIXTURES / "codex.jsonl"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("valid codex", result.stderr)
