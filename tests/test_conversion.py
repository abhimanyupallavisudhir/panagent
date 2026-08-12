from __future__ import annotations

import json
import unittest
from pathlib import Path

from panagent.errors import AcquisitionError
from panagent.readers import read_claude_code, read_codex
from panagent.web import read_chatgpt_share, read_claude_share
from panagent.writers import write_claude_code, write_codex

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def block_types(conv: dict) -> list[str]:
    return [block["type"] for item in conv["messages"] for block in item["content"]]


class NativeReaderTests(unittest.TestCase):
    def test_claude_code_reader_preserves_tools_and_warns_on_snapshot(self) -> None:
        conv = read_claude_code(fixture("claude-code.jsonl"), source_uri="fixture")
        self.assertEqual(conv["id"], "11111111-1111-4111-8111-111111111111")
        self.assertEqual([item["role"] for item in conv["messages"]], ["user", "assistant", "tool", "assistant"])
        self.assertIn("tool_call", block_types(conv))
        self.assertIn("tool_result", block_types(conv))
        self.assertEqual(conv["messages"][1]["content"][1]["id"], "toolu_fixture")
        self.assertIn("claude_file_history_snapshot_not_represented", {item["code"] for item in conv["warnings"]})

    def test_codex_reader_uses_response_items_without_event_duplicates(self) -> None:
        conv = read_codex(fixture("codex.jsonl"), source_uri="fixture")
        self.assertEqual(conv["id"], "22222222-2222-4222-8222-222222222222")
        self.assertEqual(len(conv["messages"]), 5)
        self.assertEqual(sum(block["type"] == "text" and block.get("text") == "Read the greeting." for item in conv["messages"] for block in item["content"]), 1)
        self.assertIn("tool_call", block_types(conv))
        self.assertIn("tool_result", block_types(conv))
        self.assertIn("codex_turn_context_target_specific", {item["code"] for item in conv["warnings"]})


class NativeRoundTripTests(unittest.TestCase):
    def test_claude_to_codex_and_back_preserves_semantic_blocks(self) -> None:
        original = read_claude_code(fixture("claude-code.jsonl"))
        codex = write_codex(original, mode="transcript", cwd="/tmp/project")
        self.assertIn('"type":"session_meta"', codex.text)
        self.assertIn('"type":"function_call"', codex.text)
        payload_types = [json.loads(line).get("payload", {}).get("type") for line in codex.text.splitlines()]
        self.assertIn("task_started", payload_types)
        self.assertIn("user_message", payload_types)
        self.assertIn("agent_message", payload_types)
        self.assertIn("task_complete", payload_types)
        self.assertLess(payload_types.index("message", 2), payload_types.index("function_call"))
        reparsed = read_codex(codex.text)
        self.assertEqual(block_types(reparsed).count("tool_call"), 1)
        self.assertEqual(block_types(reparsed).count("tool_result"), 1)
        claude = write_claude_code(reparsed, mode="transcript", cwd="/tmp/project")
        final = read_claude_code(claude.text)
        texts = [block.get("text") for item in final["messages"] for block in item["content"] if block["type"] == "text"]
        self.assertIn("The greeting is hello.", texts)

    def test_codex_to_claude_and_back_preserves_call_identity(self) -> None:
        original = read_codex(fixture("codex.jsonl"))
        claude = write_claude_code(original, mode="transcript", cwd="/tmp/project")
        self.assertIn('"type":"tool_use"', claude.text)
        self.assertIn('"tool_use_id":"call_fixture"', claude.text)
        reparsed = read_claude_code(claude.text)
        codex = write_codex(reparsed, mode="transcript", cwd="/tmp/project")
        records = [json.loads(line) for line in codex.text.splitlines()]
        calls = [item["payload"] for item in records if item["type"] == "response_item" and item["payload"]["type"] == "function_call"]
        results = [item["payload"] for item in records if item["type"] == "response_item" and item["payload"]["type"] == "function_call_output"]
        self.assertEqual(calls[0]["call_id"], results[0]["call_id"])

    def test_generated_native_sessions_embed_source_provenance(self) -> None:
        conv = read_codex(fixture("codex.jsonl"))
        claude_first = json.loads(write_claude_code(conv).text.splitlines()[0])
        codex_first = json.loads(write_codex(conv).text.splitlines()[0])
        self.assertEqual(claude_first["panagent"]["source"]["format"], "codex-jsonl")
        self.assertEqual(codex_first["payload"]["panagent"]["source"]["format"], "codex-jsonl")

    def test_generated_session_reimport_retains_upstream_lineage(self) -> None:
        original = read_claude_code(fixture("claude-code.jsonl"))
        reparsed = read_codex(write_codex(original).text)
        self.assertEqual(reparsed["source"]["upstream"]["format"], "claude-code-jsonl")
        provenance = reparsed["messages"][0]["provenance"]
        self.assertEqual(provenance["upstream"]["source_format"], "claude-code-jsonl")
        self.assertIn("claude_file_history_snapshot_not_represented", {item["code"] for item in reparsed["warnings"]})


class ShareReaderTests(unittest.TestCase):
    def test_current_chatgpt_react_router_payload(self) -> None:
        conv = read_chatgpt_share(fixture("chatgpt-share.html"), source_uri="https://chatgpt.com/share/fixture")
        self.assertEqual(conv["title"], "Fixture Chat")
        self.assertEqual([item["role"] for item in conv["messages"]], ["user", "assistant"])
        self.assertEqual(conv["messages"][1]["content"], [{"type": "code", "language": "bash", "text": "echo hello"}])
        self.assertIn("share_snapshot_limitations", {item["code"] for item in conv["warnings"]})

    def test_claude_browser_export_json(self) -> None:
        conv = read_claude_share(fixture("claude-share-export.json"))
        self.assertEqual(conv["title"], "Claude fixture")
        self.assertEqual([item["role"] for item in conv["messages"]], ["user", "assistant"])
        self.assertEqual(conv["source"]["kind"], "public-share-snapshot")

    def test_claude_rendered_dom_fallback(self) -> None:
        conv = read_claude_share(fixture("claude-rendered.html"), source_uri="saved.html")
        self.assertEqual(len(conv["messages"]), 2)
        self.assertIn("code()", conv["messages"][1]["content"][0]["text"])
        self.assertIn("dom_fallback", {item["code"] for item in conv["warnings"]})

    def test_claude_challenge_is_not_parser_success(self) -> None:
        with self.assertRaisesRegex(AcquisitionError, "anti-bot challenge"):
            read_claude_share(fixture("claude-challenge.html"))

    def test_web_share_context_mode_has_explicit_trust_boundary(self) -> None:
        conv = read_claude_share(fixture("claude-share-export.json"))
        output = write_codex(conv, mode="context")
        self.assertIn("untrusted context", output.text)
        self.assertIn("does not override current system", output.text)
        self.assertEqual(len([line for line in output.text.splitlines() if '"type":"message"' in line]), 1)
        metadata = json.loads(output.text.splitlines()[0])["payload"]["panagent"]
        self.assertIn("context_mode_flattened", {item["code"] for item in metadata["target_warnings"]})
