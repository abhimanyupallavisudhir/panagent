from __future__ import annotations

import os
import unittest

from panagent.errors import AcquisitionError
from panagent.web import fetch_share, read_chatgpt_share, read_claude_share


@unittest.skipUnless(os.environ.get("PANAGENT_LIVE_TESTS") == "1", "set PANAGENT_LIVE_TESTS=1 for network tests")
class LiveShareTests(unittest.TestCase):
    def test_public_chatgpt_sample(self) -> None:
        url = "https://chatgpt.com/share/6a781aea-4d3c-83eb-bf25-7d49ca647800"
        conv = read_chatgpt_share(fetch_share(url), source_uri=url)
        self.assertGreaterEqual(len(conv["messages"]), 2)
        self.assertEqual(conv["source"]["uri"], url)

    def test_public_claude_sample_or_explicit_challenge(self) -> None:
        url = "https://claude.ai/share/3d69a25c-b702-4a46-914f-074ead8cf064"
        text = fetch_share(url)
        try:
            conv = read_claude_share(text, source_uri=url)
        except AcquisitionError as exc:
            self.assertIn("anti-bot challenge", str(exc))
        else:
            self.assertGreaterEqual(len(conv["messages"]), 2)
