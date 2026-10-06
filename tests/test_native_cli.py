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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from panagent.api import install
from panagent.readers import read_claude_code, read_codex


FIXTURES = Path(__file__).parent / "fixtures"
SESSION_ID = "11111111-1111-4111-8111-111111111111"
# karmax pins the Codex release that reads imported rollouts; a sibling checkout
# with installed dependencies has it offline.
PINNED_CODEX = Path(__file__).resolve().parents[2] / "karmax" / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"


@unittest.skipUnless(os.environ.get("PANAGENT_NATIVE_TESTS") == "1", "set PANAGENT_NATIVE_TESTS=1 for installed-CLI checks")
class CodexNativeCompatibilityTests(unittest.TestCase):
    def test_current_codex_reads_and_resumes_generated_rollout(self) -> None:
        executable = shutil.which("codex")
        if not executable:
            self.skipTest("codex is not installed")
        _assert_codex_reads_and_resumes(self, [executable])


class PinnedCodexCompatibilityTests(unittest.TestCase):
    def test_pinned_codex_reads_and_resumes_generated_rollout(self) -> None:
        configured = os.environ.get("PANAGENT_PINNED_CODEX")
        if configured:
            command = shlex.split(configured)
        elif PINNED_CODEX.is_file() and shutil.which("node"):
            command = ["node", str(PINNED_CODEX)]
        else:
            self.skipTest(f"pinned Codex is not installed at {PINNED_CODEX}")
        _assert_codex_reads_and_resumes(self, command)


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
            install(conversation, "claude-code", cwd=project, session_id="22222222-2222-4222-8222-222222222222",
                    home=home / ".claude")
            # Run as a stranger: no inherited Claude config or credentials (a
            # parent Claude session's would redirect discovery and spend money).
            environment = {key: value for key, value in os.environ.items()
                           if not key.startswith(("CLAUDE", "ANTHROPIC"))}
            environment["HOME"] = str(home)
            environment["CLAUDE_CONFIG_DIR"] = str(home / ".claude")
            environment["ANTHROPIC_API_KEY"] = "invalid-panagent-native-test"
            # A local stand-in for the API records what Claude sends and refuses
            # it, proving the resumed history reaches the model without spending.
            with _RefusingAPI() as api:
                environment["ANTHROPIC_BASE_URL"] = api.url
                process = subprocess.Popen(
                    [*command, "--bare", "--resume", "22222222-2222-4222-8222-222222222222", "--print",
                     "--tools", "", "--max-budget-usd", "0.01", "Reply PONG."],
                    cwd=project, env=environment, text=True, stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                )
                try:
                    # Claude retries a refused key with backoff; the first attempt is the evidence.
                    api.message.wait(60)
                finally:
                    process.kill()
                    output = process.communicate()[0]
            self.assertNotIn("No conversation found", output)
            self.assertTrue(api.bodies, output)
            sent = api.bodies[0]
            self.assertIn("Read the greeting.", sent)  # the imported history...
            self.assertLess(sent.index("Read the greeting."), sent.index("Reply PONG."))  # ...then the new prompt


class _RefusingAPI:
    """An HTTP server on localhost that answers every request with 401 and keeps the bodies."""

    def __enter__(self) -> "_RefusingAPI":
        bodies: list[str] = []
        message = threading.Event()
        self.bodies, self.message = bodies, message

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                body = self.rfile.read(int(self.headers.get("content-length") or 0)).decode("utf-8", "replace")
                if self.path.startswith("/v1/messages"):
                    bodies.append(body)
                    message.set()
                payload = b'{"type":"error","error":{"type":"authentication_error","message":"invalid x-api-key"}}'
                self.send_response(401)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            do_GET = do_HEAD = do_POST  # noqa: N815

            def log_message(self, *_: Any) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        return self

    def __exit__(self, *_: Any) -> None:
        self.server.shutdown()
        self.server.server_close()


def _assert_codex_reads_and_resumes(test: unittest.TestCase, command: list[str]) -> None:
    conversation = read_claude_code((FIXTURES / "claude-code.jsonl").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as directory:
        codex_home = Path(directory)
        # Installed exactly where `panagent convert --install` puts it, so this
        # also proves Codex discovers sessions at that path.
        install(conversation, "codex", cwd="/tmp", session_id=SESSION_ID, home=codex_home)
        client = _AppServer(command, codex_home)
        try:
            client.request(
                1,
                "initialize",
                {"clientInfo": {"name": "panagent-test", "title": "panagent test", "version": "0.1.0"}},
            )
            client.notify("initialized", {})
            read = client.request(2, "thread/read", {"threadId": SESSION_ID, "includeTurns": True})
            thread = read["result"]["thread"]
            test.assertEqual(thread["id"], SESSION_ID)
            test.assertGreaterEqual(len(thread["turns"]), 1)
            item_types = [item["type"] for turn in thread["turns"] for item in turn["items"]]
            test.assertIn("userMessage", item_types)
            test.assertIn("agentMessage", item_types)
            resumed = client.request(3, "thread/resume", {"threadId": SESSION_ID})
            test.assertEqual(resumed["result"]["thread"]["id"], SESSION_ID)
        finally:
            client.close()


class _AppServer:
    def __init__(self, command: list[str], codex_home: Path) -> None:
        environment = os.environ.copy()
        environment["CODEX_HOME"] = str(codex_home)
        self.process = subprocess.Popen(
            [*command, "app-server", "--stdio"],
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
