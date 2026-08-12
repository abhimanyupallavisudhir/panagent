from __future__ import annotations

import json
import os
import queue
import shlex
import shutil
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from typing import Any

from panagent.readers import read_claude_code, read_codex
from panagent.writers import write_claude_code, write_codex


FIXTURES = Path(__file__).parent / "fixtures"
SESSION_ID = "11111111-1111-4111-8111-111111111111"


@unittest.skipUnless(os.environ.get("PANAGENT_NATIVE_TESTS") == "1", "set PANAGENT_NATIVE_TESTS=1 for installed-CLI checks")
class CodexNativeCompatibilityTests(unittest.TestCase):
    def test_current_codex_reads_and_resumes_generated_rollout(self) -> None:
        executable = shutil.which("codex")
        if not executable:
            self.skipTest("codex is not installed")
        conversation = read_claude_code((FIXTURES / "claude-code.jsonl").read_text(encoding="utf-8"))
        rendered = write_codex(conversation, mode="transcript", cwd="/tmp/panagent-native-test")
        with tempfile.TemporaryDirectory() as directory:
            codex_home = Path(directory)
            sessions = codex_home / "sessions" / "2026" / "08" / "11"
            sessions.mkdir(parents=True)
            rollout = sessions / f"rollout-2026-08-11T00-00-00-{SESSION_ID}.jsonl"
            rollout.write_text(rendered.text, encoding="utf-8")
            client = _AppServer(executable, codex_home)
            try:
                client.request(
                    1,
                    "initialize",
                    {"clientInfo": {"name": "panagent-test", "title": "panagent test", "version": "0.1.0"}},
                )
                client.notify("initialized", {})
                read = client.request(2, "thread/read", {"threadId": SESSION_ID, "includeTurns": True})
                thread = read["result"]["thread"]
                self.assertEqual(thread["id"], SESSION_ID)
                self.assertGreaterEqual(len(thread["turns"]), 1)
                item_types = [item["type"] for turn in thread["turns"] for item in turn["items"]]
                self.assertIn("userMessage", item_types)
                self.assertIn("agentMessage", item_types)
                resumed = client.request(3, "thread/resume", {"threadId": SESSION_ID})
                self.assertEqual(resumed["result"]["thread"]["id"], SESSION_ID)
            finally:
                client.close()


@unittest.skipUnless(os.environ.get("PANAGENT_CLAUDE_TESTS") == "1", "set PANAGENT_CLAUDE_TESTS=1 for Claude CLI discovery")
class ClaudeNativeCompatibilityTests(unittest.TestCase):
    def test_current_claude_discovers_generated_session(self) -> None:
        command = shlex.split(os.environ.get("PANAGENT_CLAUDE_COMMAND", "claude"))
        if not command or not shutil.which(command[0]):
            self.skipTest("Claude Code is not installed")
        conversation = read_codex((FIXTURES / "codex.jsonl").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            project = home / "project"
            project.mkdir()
            encoded = str(project).replace("/", "-").replace(".", "-")
            sessions = home / ".claude" / "projects" / encoded
            sessions.mkdir(parents=True)
            session = sessions / "22222222-2222-4222-8222-222222222222.jsonl"
            session.write_text(write_claude_code(conversation, cwd=str(project)).text, encoding="utf-8")
            environment = os.environ.copy()
            environment["HOME"] = str(home)
            # A deliberately invalid key proves that Claude discovered and parsed
            # the history far enough to attempt the API call, without spending or
            # depending on a developer's personal login.
            environment["ANTHROPIC_API_KEY"] = "invalid-panagent-native-test"
            result = subprocess.run(
                [
                    *command,
                    "--bare",
                    "--resume",
                    "22222222-2222-4222-8222-222222222222",
                    "--print",
                    "--tools",
                    "",
                    "--max-budget-usd",
                    "0.01",
                    "Reply PONG.",
                ],
                cwd=project,
                env=environment,
                text=True,
                capture_output=True,
                timeout=30,
                check=False,
            )
            combined = f"{result.stdout}\n{result.stderr}"
            self.assertNotIn("No conversation found", combined)
            self.assertIn("Invalid API key", combined)


class _AppServer:
    def __init__(self, executable: str, codex_home: Path) -> None:
        environment = os.environ.copy()
        environment["CODEX_HOME"] = str(codex_home)
        self.process = subprocess.Popen(
            [executable, "app-server", "--stdio"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            env=environment,
        )
        self.messages: queue.Queue[dict[str, Any]] = queue.Queue()
        assert self.process.stdout is not None
        self.reader = threading.Thread(target=self._read, args=(self.process.stdout,), daemon=True)
        self.reader.start()

    def _read(self, stream: Any) -> None:
        for line in stream:
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                self.messages.put(value)

    def _send(self, value: dict[str, Any]) -> None:
        if self.process.stdin is None:
            raise AssertionError("Codex app-server stdin is unavailable")
        self.process.stdin.write(json.dumps(value, separators=(",", ":")) + "\n")
        self.process.stdin.flush()

    def notify(self, method: str, params: dict[str, Any]) -> None:
        self._send({"method": method, "params": params})

    def request(self, identifier: int, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self._send({"method": method, "id": identifier, "params": params})
        while True:
            try:
                value = self.messages.get(timeout=15)
            except queue.Empty as exc:
                stderr = self.process.stderr.read() if self.process.poll() is not None and self.process.stderr else ""
                raise AssertionError(f"timed out waiting for Codex {method}: {stderr}") from exc
            if value.get("id") == identifier:
                if "error" in value:
                    raise AssertionError(f"Codex {method} failed: {value['error']}")
                return value

    def close(self) -> None:
        if self.process.stdin is not None:
            self.process.stdin.close()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            self.process.wait(timeout=5)
        if self.process.stdout is not None:
            self.process.stdout.close()
        if self.process.stderr is not None:
            self.process.stderr.close()
