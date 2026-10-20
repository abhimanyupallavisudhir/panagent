from __future__ import annotations

import json
import unittest
from pathlib import Path
from urllib.parse import urlparse

from panagent.api import parse
from panagent.detect import detect_text, url_format
from panagent.errors import FormatError
from panagent.shares import SITES, share_site

FIXTURES = Path(__file__).parent / "fixtures"
Q, A = "What is the capital of France?", "The capital of France is **Paris**."


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def texts(conv: dict) -> list[tuple[str, str]]:
    return [(m["role"], b["text"]) for m in conv["messages"] for b in m["content"] if b["type"] == "text"]


class ShareSiteTests(unittest.TestCase):
    """Each fixture has the shape of the site's real answer (checked against
    real public shares, 2026-10-20), with made-up text."""

    def test_every_site_reads_its_answer(self) -> None:
        cases = {
            "deepseek-share.json": ("deepseek-share", None, None),
            "grok-share.json": ("grok-share", "Capitals fixture", "grok-4"),
            "perplexity-share.json": ("perplexity-share", "Capitals fixture", "pplx_pro"),
            "poe-share.html": ("poe-share", "Capitals fixture", "GPT-4o"),
            "mistral-share.html": ("mistral-share", "Capitals fixture", None),
            "kimi-share.json": ("kimi-share", "Capitals fixture", None),
            "qwen-share.json": ("qwen-share", "Capitals fixture", "Qwen3.5-Plus"),
        }
        for name, (fmt, title, model) in cases.items():
            with self.subTest(name=name):
                text = fixture(name)
                self.assertEqual(detect_text(text), fmt)
                conv = parse(text)
                self.assertEqual(conv["source"]["format"], fmt)
                self.assertEqual(conv["source"]["kind"], "public-share-snapshot")
                self.assertEqual(conv["title"], title)
                self.assertEqual(conv["environment"].get("model"), model)
                self.assertEqual(texts(conv)[:2], [("user", Q), ("assistant", A)])
                self.assertEqual(len({m["id"] for m in conv["messages"]}), len(conv["messages"]))

    def test_reasoning_stays_apart_from_the_answer(self) -> None:
        for name, thought in (("deepseek-share.json", "France's capital is well known."),
                              ("mistral-share.html", "The user asks a geography question."),
                              ("qwen-share.json", "Recall the capital.")):
            with self.subTest(name=name):
                answer = parse(fixture(name))["messages"][1]["content"]
                self.assertEqual(answer[0], {"type": "reasoning", "text": thought, "visibility": "source-visible"})
                self.assertEqual(answer[-1]["text"], A)

    def test_what_is_not_carried_is_said(self) -> None:
        self.assertIn("share_partial", {w["code"] for w in parse(fixture("poe-share.html"))["warnings"]})
        self.assertIn("mistral_chunk_not_represented", {w["code"] for w in parse(fixture("mistral-share.html"))["warnings"]})
        kimi = parse(fixture("kimi-share.json"))
        self.assertIn({"type": "attachment", "name": "notes.pdf"}, kimi["messages"][0]["content"])
        perplexity = parse(fixture("perplexity-share.json"))
        self.assertEqual(texts(perplexity)[2:], [("user", "And of Italy?"), ("assistant", "Rome.")])

    def test_an_unshared_or_deleted_share_says_so(self) -> None:
        answers = {
            "deepseek-share": {"code": 0, "msg": "", "data": {"biz_code": 1, "biz_msg": "share does not exist", "biz_data": None}},
            "grok-share": {"code": 5, "message": "Cannot find conversation."},
            "perplexity-share": {"detail": {"error_code": "THREAD_NOT_FOUND"}},
            "kimi-share": {"code": "not_found", "message": "Chat session not found"},
            "qwen-share": {"success": False, "data": {"code": "Not_Found"}},
        }
        for fmt, answer in answers.items():
            with self.subTest(fmt=fmt), self.assertRaisesRegex(FormatError, "unavailable; it may have been deleted or unshared"):
                parse(json.dumps(answer), fmt)
        with self.assertRaisesRegex(FormatError, "unavailable"):
            parse('<script id="__NEXT_DATA__" type="application/json">{"props":{"pageProps":{"data":null,"errorCode":404}}}</script>', "poe-share")
        with self.assertRaisesRegex(FormatError, "not public, or does not exist"):
            parse('<script>self.__next_f.push([1,"1:[\\"$\\",\\"div\\",null,{\\"children\\":\\"This chat does not exist\\"}]\\n"])</script>', "mistral-share")

    def test_links_and_the_requests_they_make(self) -> None:
        expected = {
            "https://chat.deepseek.com/share/ewfxrfhb7obmide29x":
                ("deepseek-share", "https://chat.deepseek.com/api/v0/share/content?share_id=ewfxrfhb7obmide29x", None),
            "https://grok.com/share/c2hhcmQtMg%3D%3D_ddbace62-c299-4b7b-921c-c5188e9cac50":
                ("grok-share", "https://grok.com/rest/app-chat/share_links_data/c2hhcmQtMg%3D%3D_ddbace62-c299-4b7b-921c-c5188e9cac50", None),
            "https://www.perplexity.ai/search/are-llms-deterministic-if-you-NhO3G2KDSVe1nlSrIioVzQ":
                ("perplexity-share", "https://www.perplexity.ai/rest/thread/are-llms-deterministic-if-you-NhO3G2KDSVe1nlSrIioVzQ?", None),
            "https://poe.com/s/Qu62LtlV2yKGZXlXTTS1": ("poe-share", "https://poe.com/s/Qu62LtlV2yKGZXlXTTS1", None),
            "https://chat.mistral.ai/chat/897fbe7d-b1ae-4109-9b29-f3ccc4f8896d":
                ("mistral-share", "https://chat.mistral.ai/chat/897fbe7d-b1ae-4109-9b29-f3ccc4f8896d", None),
            "https://www.kimi.com/share/en/d2fvbevhq49s4blc862g":
                ("kimi-share", "https://www.kimi.com/apiv2/kimi.gateway.chat.v1.ChatService/GetChatShare", b'{"share_id": "d2fvbevhq49s4blc862g"}'),
            "https://chat.qwen.ai/s/b6bb9ca0-8565-4040-8c58-9c45a538be47":
                ("qwen-share", "https://chat.qwen.ai/api/v2/chats/share/b6bb9ca0-8565-4040-8c58-9c45a538be47", None),
        }
        for link, (fmt, target, body) in expected.items():
            with self.subTest(link=link):
                self.assertEqual(url_format(link), fmt)
                site, share_id = share_site(urlparse(link))
                url, data, _headers = site.request(share_id)
                self.assertTrue(url.startswith(target), url)
                self.assertEqual(data, body)
        for link in ("https://chat.mistral.ai/chat", "https://poe.com/chat/abc", "https://grok.com/chat/abc",
                     "https://chat.deepseek.com/a/chat/s/abc", "https://evil.example/s/abc"):
            with self.subTest(link=link):
                self.assertIsNone(share_site(urlparse(link)))
        self.assertEqual(len({site.format for site in SITES}), len(SITES))


if __name__ == "__main__":
    unittest.main()
