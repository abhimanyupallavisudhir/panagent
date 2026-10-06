from __future__ import annotations

import os
import unittest

from panagent.errors import AcquisitionError, BrowserRequired
from panagent.web import fetch_share, read_chatgpt_share, read_claude_share


@unittest.skipUnless(os.environ.get("PANAGENT_LIVE_TESTS") == "1", "set PANAGENT_LIVE_TESTS=1 for network tests")
class LiveShareTests(unittest.TestCase):
    def test_public_chatgpt_sample(self) -> None:
        url = "https://chatgpt.com/share/6a781aea-4d3c-83eb-bf25-7d49ca647800"
        conv = read_chatgpt_share(fetch_share(url), source_uri=url)
        self.assertGreaterEqual(len(conv["messages"]), 2)
        self.assertEqual(conv["source"]["uri"], url)

    def test_public_claude_sample_or_explicit_browser_boundary(self) -> None:
        # Plain HTTP gets either a challenge or (seen 2026-09-28) a 127 KB app
        # shell whose only marker is Cloudflare's ordinary challenge-platform
        # script; both must ask for a browser, and only the first is a challenge.
        url = "https://claude.ai/share/3d69a25c-b702-4a46-914f-074ead8cf064"
        text = fetch_share(url)
        try:
            conv = read_claude_share(text, source_uri=url)
        except BrowserRequired as exc:
            self.assertRegex(str(exc), "anti-bot challenge|renders only in a browser")
        else:
            self.assertGreaterEqual(len(conv["messages"]), 2)

    def test_tavya_unknown_share_is_not_found(self) -> None:
        url = "https://tavya.io/share/conversations/" + "A" * 43
        with self.assertRaisesRegex(AcquisitionError, "share not found") as caught:
            fetch_share(url)
        self.assertEqual(caught.exception.status, 404)
