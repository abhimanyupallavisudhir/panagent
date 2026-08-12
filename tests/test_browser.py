from __future__ import annotations

import argparse
import unittest
from pathlib import Path
from unittest.mock import patch

from panagent.browser import fetch_share_browser
from panagent.cli import _load
from panagent.errors import AcquisitionError


FIXTURES = Path(__file__).parent / "fixtures"


class BrowserFallbackTests(unittest.TestCase):
    def test_cdp_rejects_non_loopback_endpoint(self) -> None:
        with self.assertRaisesRegex(AcquisitionError, "restricted to loopback"):
            fetch_share_browser("https://claude.ai/share/fixture", cdp_url="http://browser.example:9222")

    def test_challenged_claude_url_retries_through_browser(self) -> None:
        args = argparse.Namespace(
            source="https://claude.ai/share/fixture",
            source_format=None,
            timeout=1.0,
            browser="auto",
            browser_timeout=20.0,
            cdp_url=None,
            browser_profile=None,
        )
        challenge = (FIXTURES / "claude-challenge.html").read_text(encoding="utf-8")
        exported = (FIXTURES / "claude-share-export.json").read_text(encoding="utf-8")
        with (
            patch("panagent.cli.fetch_share", return_value=challenge),
            patch("panagent.cli.fetch_share_browser", return_value=exported) as browser,
        ):
            conversation, source_format = _load(args, allow_url=True)
        self.assertEqual(source_format, "claude-share")
        self.assertEqual(len(conversation["messages"]), 2)
        browser.assert_called_once_with(
            args.source,
            timeout=20.0,
            mode="auto",
            profile=None,
        )

    def test_http_acquisition_failure_retries_through_browser(self) -> None:
        args = argparse.Namespace(
            source="https://claude.ai/share/fixture",
            source_format=None,
            timeout=1.0,
            browser="auto",
            browser_timeout=20.0,
            cdp_url=None,
            browser_profile=None,
        )
        exported = (FIXTURES / "claude-share-export.json").read_text(encoding="utf-8")
        with (
            patch("panagent.cli.fetch_share", side_effect=AcquisitionError("HTTP 403")),
            patch("panagent.cli.fetch_share_browser", return_value=exported) as browser,
        ):
            conversation, source_format = _load(args, allow_url=True)
        self.assertEqual(source_format, "claude-share")
        self.assertEqual(len(conversation["messages"]), 2)
        browser.assert_called_once()

    def test_cdp_uses_browser_without_plain_http(self) -> None:
        args = argparse.Namespace(
            source="https://claude.ai/share/fixture",
            source_format=None,
            timeout=1.0,
            browser="auto",
            browser_timeout=20.0,
            cdp_url="http://127.0.0.1:9222",
            browser_profile=None,
        )
        exported = (FIXTURES / "claude-share-export.json").read_text(encoding="utf-8")
        with (
            patch("panagent.cli.fetch_share") as plain,
            patch("panagent.cli.fetch_share_browser", return_value=exported) as browser,
        ):
            conversation, _ = _load(args, allow_url=True)
        self.assertEqual(len(conversation["messages"]), 2)
        plain.assert_not_called()
        browser.assert_called_once_with(
            args.source,
            timeout=20.0,
            mode="auto",
            cdp_url=args.cdp_url,
            profile=None,
        )
