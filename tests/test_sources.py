from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

import panagent
from panagent.detect import detect_text, url_format
from panagent.errors import AcquisitionError, FormatError
from panagent.web import _ShareRedirectHandler, fetch_share, read_tavya_share

FIXTURES = Path(__file__).parent / "fixtures"
TAVYA_URL = "https://tavya.io/share/conversations/Zm9vYmFyYmF6cXV4Zm9vYmFyYmF6cXV4Zm9vYmFyYmF"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def texts(conv: dict) -> list[str]:
    return [block.get("text") for item in conv["messages"] for block in item["content"]]


class TavyaShareTests(unittest.TestCase):
    """tavya-share.html is the output of karmax's own publicConversationHtml."""

    def test_reads_exact_message_source_text(self) -> None:
        conv = read_tavya_share(fixture("tavya-share.html"), source_uri=TAVYA_URL)
        self.assertEqual(conv["title"], 'Port the <parser> & "tests"')
        self.assertEqual(conv["id"], TAVYA_URL.rsplit("/", 1)[1])
        self.assertEqual(conv["source"]["provider"], "tavya")
        self.assertEqual(conv["source"]["uri"], TAVYA_URL)
        self.assertEqual(conv["updated_at"], "2026-10-05T12:30:00.000Z")
        self.assertEqual([item["role"] for item in conv["messages"]], ["user", "assistant", "user"])
        self.assertEqual(texts(conv)[0], 'Rewrite `parse()` so it handles <tags> & "quotes".\n\nKeep ChatGPT exports working.')
        # Markdown indentation and math survive byte for byte.
        self.assertIn("```python\nfor line in lines:\n    if not line.strip():\n        continue\n```", texts(conv)[1])
        self.assertIn(r"$a < b$ and \(x > y\). Unicode: café — ✓", texts(conv)[1])
        # Escaped markup in a message stays text and cannot forge a message.
        self.assertTrue(texts(conv)[2].startswith('</div></article><article data-share-message class="msg agent">'))
        self.assertEqual({w["code"] for w in conv["warnings"]}, {"share_snapshot_limitations"})

    def test_detected_by_url_on_tavya_and_self_hosted_karmax(self) -> None:
        self.assertEqual(url_format(TAVYA_URL), "tavya-share")
        self.assertEqual(url_format(TAVYA_URL.replace("tavya.io", "karmax.example.org")), "tavya-share")
        for url in ("https://tavya.io/share/conversations/short", "https://tavya.io/tasks/123"):
            with self.subTest(url), self.assertRaises(FormatError):
                url_format(url)

    def test_saved_page_is_detected_even_when_it_discusses_other_providers(self) -> None:
        self.assertEqual(detect_text(fixture("tavya-share.html")), "tavya-share")
        self.assertEqual(panagent.parse(fixture("tavya-share.html"))["source"]["format"], "tavya-share-html")

    def test_revoked_share_is_an_error_not_an_empty_conversation(self) -> None:
        html = fixture("tavya-share.html")
        unavailable = html[: html.index('<main class="shared-main">')] + (
            '<main class="shared-main"><section class="shared-unavailable"><h1>Conversation unavailable</h1></section></main>')
        with self.assertRaisesRegex(FormatError, "revoked"):
            read_tavya_share(unavailable)

    def test_url_import_uses_plain_https_and_never_a_browser(self) -> None:
        with (patch("panagent.api.fetch_share", return_value=fixture("tavya-share.html")) as plain,
              patch("panagent.api.fetch_share_browser") as browser):
            conv = panagent.load(TAVYA_URL, browser="auto")
        plain.assert_called_once()
        self.assertEqual(len(conv["messages"]), 3)
        with (patch("panagent.api.fetch_share", side_effect=AcquisitionError("HTTP 429", status=429)),
              patch("panagent.api.fetch_share_browser") as browser):
            with self.assertRaises(AcquisitionError):
                panagent.load(TAVYA_URL, browser="headed")
        browser.assert_not_called()

    def test_missing_share_reports_not_found(self) -> None:
        error = HTTPError(TAVYA_URL, 404, "Not Found", {}, None)  # type: ignore[arg-type]
        with patch("panagent.web.build_opener") as opener:
            opener.return_value.open.side_effect = error
            with self.assertRaisesRegex(AcquisitionError, "share not found") as caught:
                fetch_share(TAVYA_URL)
        self.assertEqual(caught.exception.status, 404)

    def test_native_targets_get_guarded_context_by_default(self) -> None:
        conv = read_tavya_share(fixture("tavya-share.html"), source_uri=TAVYA_URL)
        rendered = panagent.render(conv, "claude-code")
        self.assertEqual(rendered.mode, "context")
        records = [json.loads(line) for line in rendered.text.splitlines()]
        self.assertEqual(len(records), 1)
        self.assertIn("Source URL: " + TAVYA_URL, records[0]["message"]["content"])


class RedirectTests(unittest.TestCase):
    def test_redirect_stays_within_one_kind_of_share(self) -> None:
        class Request:
            full_url = "https://chat.openai.com/share/abc"
            headers: dict = {}
            unredirected_hdrs: dict = {}
            origin_req_host = "chat.openai.com"

            def get_method(self) -> str:
                return "GET"

        handler = _ShareRedirectHandler()
        self.assertIsNotNone(handler.redirect_request(Request(), None, 301, "Moved", {}, "https://chatgpt.com/share/abc"))
        with self.assertRaisesRegex(AcquisitionError, "different kind"):
            handler.redirect_request(Request(), None, 302, "Found", {}, TAVYA_URL)


class ChatGPTExportTests(unittest.TestCase):
    def test_multi_conversation_export_requires_a_choice(self) -> None:
        self.assertEqual(detect_text(fixture("chatgpt-export.json")), "chatgpt-share")
        with self.assertRaisesRegex(FormatError, "2 conversations; choose one with --conversation"):
            panagent.parse(fixture("chatgpt-export.json"))

    def test_selected_conversation_follows_the_active_branch(self) -> None:
        for wanted in ("68000000-0000-4000-8000-000000000001", "Plot the data"):
            with self.subTest(wanted):
                conv = panagent.parse(fixture("chatgpt-export.json"), conversation=wanted)
                self.assertEqual(conv["title"], "Plot the data")
                self.assertEqual(conv["source"]["kind"], "account-export")
                self.assertEqual(conv["source"]["format"], "chatgpt-export-json")
                self.assertEqual([item["role"] for item in conv["messages"]], ["user", "assistant", "tool", "assistant"])
                user = conv["messages"][0]["content"]
                self.assertEqual(user[0], {"type": "attachment", "name": "file-service://file-abc", "media_type": "image"})
                self.assertEqual(user[1]["text"], "Plot this chart.")
                self.assertEqual(conv["messages"][2]["content"][0]["content"], "<Figure 1>")
                self.assertNotIn("An abandoned branch.", json.dumps(conv))
                self.assertNotIn("secret profile", json.dumps(conv))
                codes = {item["code"] for item in conv["warnings"]}
                self.assertTrue({"chatgpt_image_unavailable", "chatgpt_model_context_not_message"} <= codes)

    def test_list_counts_the_messages_a_conversion_keeps(self) -> None:
        from panagent.web import list_conversations
        rows = list_conversations(fixture("chatgpt-export.json"), "chatgpt-share")
        self.assertEqual([(row["title"], row["messages"]) for row in rows], [("Plot the data", 4), ("Second chat", 2)])

    def test_unknown_choice_is_an_error(self) -> None:
        with self.assertRaisesRegex(FormatError, "no conversation"):
            panagent.parse(fixture("chatgpt-export.json"), conversation="missing")


class ClaudeExportTests(unittest.TestCase):
    def conv(self) -> dict:
        return panagent.parse(fixture("claude-export.json"), conversation="Research the API")

    def test_web_tool_use_becomes_paired_native_structure(self) -> None:
        conv = self.conv()
        self.assertEqual(conv["source"]["kind"], "account-export")
        self.assertEqual([item["role"] for item in conv["messages"]], ["user", "assistant", "tool", "assistant"])
        self.assertEqual(len({item["id"] for item in conv["messages"]}), 4)
        assistant = conv["messages"][1]["content"]
        self.assertEqual([block["type"] for block in assistant], ["reasoning", "tool_call"])
        self.assertEqual(conv["messages"][2]["content"][0],
                         {"type": "tool_result", "tool_call_id": "toolu_1", "content": "result one", "is_error": False})
        records = [json.loads(line) for line in panagent.render(conv, "claude-code", mode="transcript").text.splitlines()]
        self.assertEqual([record["type"] for record in records], ["user", "assistant", "user", "assistant"])
        self.assertEqual(records[2]["message"]["content"][0]["tool_use_id"], "toolu_1")

    def test_attachment_contents_are_carried_not_dropped(self) -> None:
        conv = self.conv()
        attachments = [block for block in conv["messages"][0]["content"] if block["type"] == "attachment"]
        self.assertEqual(attachments[0], {"type": "attachment", "name": "notes.txt", "media_type": "text/plain", "text": "alpha\nbeta"})
        self.assertEqual(attachments[1], {"type": "attachment", "name": "diagram.png"})
        markdown = panagent.render(conv, "markdown").text
        self.assertIn("[Attachment: notes.txt]\n\n```text\nalpha\nbeta\n```", markdown)
        context = panagent.render(conv, "codex").text
        self.assertIn("[Attachment: notes.txt]\\nalpha\\nbeta", context)

    def test_single_conversation_export_needs_no_choice(self) -> None:
        one = json.dumps([json.loads(fixture("claude-export.json"))[1]])
        self.assertEqual(texts(panagent.parse(one)), ["Ping"])
