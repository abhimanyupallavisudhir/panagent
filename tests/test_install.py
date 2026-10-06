from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import panagent
from panagent.errors import PanagentError

ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


class InstallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.project = self.root / "my project.v2"
        self.project.mkdir()
        self.conv = panagent.load(FIXTURES / "codex.jsonl")

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_claude_session_lands_in_its_project_directory(self) -> None:
        installed = panagent.install(self.conv, "claude", cwd=self.project, home=self.root / "claude")
        slug = re.sub(r"[^A-Za-z0-9]", "-", str(self.project.resolve()))  # Claude Code's project key
        self.assertEqual(installed.path, self.root / "claude" / "projects" / slug / f"{installed.session_id}.jsonl")
        self.assertNotEqual(installed.session_id, self.conv["id"])
        records = [json.loads(line) for line in installed.path.read_text().splitlines()]
        self.assertTrue(all(record["sessionId"] == installed.session_id for record in records))
        self.assertTrue(all(record["cwd"] == str(self.project.resolve()) for record in records))
        self.assertEqual(installed.command, f"cd '{self.project.resolve()}' && claude --resume {installed.session_id}")
        self.assertEqual(installed.path.stat().st_mode & 0o777, 0o600)

    def test_codex_rollout_is_dated_by_its_session_start(self) -> None:
        installed = panagent.install(self.conv, "codex", session_id="13a24696-e6c4-4f2e-bf29-4234eac1af21",
                                     home=self.root / "codex")
        self.assertEqual(installed.path, self.root / "codex" / "sessions" / "2026" / "08" / "01"
                         / "rollout-2026-08-01T11-00-00-13a24696-e6c4-4f2e-bf29-4234eac1af21.jsonl")
        self.assertEqual(installed.command, "codex resume 13a24696-e6c4-4f2e-bf29-4234eac1af21")
        meta = json.loads(installed.path.read_text().splitlines()[0])
        self.assertEqual(meta["payload"]["id"], installed.session_id)

    def test_environment_selects_the_cli_home(self) -> None:
        with patch.dict(os.environ, {"CODEX_HOME": str(self.root / "env-codex")}):
            installed = panagent.install(self.conv, "codex")
        self.assertTrue(str(installed.path).startswith(str(self.root / "env-codex" / "sessions")))

    def test_existing_session_is_never_overwritten(self) -> None:
        options = dict(session_id="13a24696-e6c4-4f2e-bf29-4234eac1af21", home=self.root / "codex")
        first = panagent.install(self.conv, "codex", **options)
        before = first.path.read_text()
        with self.assertRaisesRegex(PanagentError, "already exists"):
            panagent.install(self.conv, "codex", **options)
        self.assertEqual(first.path.read_text(), before)

    def test_cli_prints_the_resume_command(self) -> None:
        environment = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "CLAUDE_CONFIG_DIR": str(self.root / "claude")}
        result = subprocess.run(
            [sys.executable, "-m", "panagent", "convert", str(FIXTURES / "chatgpt-share.html"), "--to", "claude", "--install"],
            cwd=self.project, env=environment, text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        command = result.stdout.strip()
        self.assertRegex(command, r"^cd '.*my project\.v2' && claude --resume [0-9a-f-]{36}$")
        session = command.rsplit(" ", 1)[1]
        installed = list((self.root / "claude" / "projects").glob(f"*/{session}.jsonl"))
        self.assertEqual(len(installed), 1)
        self.assertIn(str(installed[0]), result.stderr)
        self.assertIn("(context)", result.stderr)

        markdown = subprocess.run(
            [sys.executable, "-m", "panagent", "convert", str(FIXTURES / "codex.jsonl"), "--to", "md", "--install"],
            env=environment, text=True, capture_output=True, check=False)
        self.assertEqual(markdown.returncode, 2)
        self.assertIn("--install needs --to claude-code or --to codex", markdown.stderr)
