from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from panagent.browser import fetch_share_browser
from panagent.api import load
from panagent.errors import AcquisitionError
from panagent.web import fetch_share, _ShareRedirectHandler


FIXTURES = Path(__file__).parent / "fixtures"


class BrowserFallbackTests(unittest.TestCase):
    def test_share_fetch_rejects_unsupported_scheme_and_redirect(self) -> None:
        with self.assertRaisesRegex(AcquisitionError, "HTTPS public share"):
            fetch_share("file:///etc/passwd")
        with self.assertRaisesRegex(AcquisitionError, "HTTPS public share"):
            _ShareRedirectHandler().redirect_request(None, None, 302, "Found", {}, "http://127.0.0.1/private")

    def test_cdp_rejects_non_loopback_endpoint(self) -> None:
        with self.assertRaisesRegex(AcquisitionError, "restricted to loopback"):
            fetch_share_browser("https://claude.ai/share/fixture", cdp_url="http://browser.example:9222")

    def test_challenged_or_unrendered_claude_url_retries_through_browser(self) -> None:
        url = "https://claude.ai/share/fixture"
        options = dict(timeout=1.0, browser="auto", browser_timeout=20.0)
        exported = (FIXTURES / "claude-share-export.json").read_text(encoding="utf-8")
        for name in ("cloudflare-challenge.html", "claude-app-shell.html"):
            with (
                self.subTest(name),
                patch("panagent.api.fetch_share", return_value=(FIXTURES / name).read_text(encoding="utf-8")),
                patch("panagent.api.fetch_share_browser", return_value=exported) as browser,
            ):
                conversation = load(url, **options)
                self.assertEqual(conversation["source"]["provider"], "anthropic")
                self.assertEqual(len(conversation["messages"]), 2)
                browser.assert_called_once_with(url, timeout=20.0, mode="auto", cdp_url=None, profile=None)

    def test_http_acquisition_failure_retries_through_browser(self) -> None:
        url = "https://claude.ai/share/fixture"
        options = dict(timeout=1.0, browser="auto", browser_timeout=20.0)
        exported = (FIXTURES / "claude-share-export.json").read_text(encoding="utf-8")
        with (
            patch("panagent.api.fetch_share", side_effect=AcquisitionError("share request returned HTTP 403", status=403)),
            patch("panagent.api.fetch_share_browser", return_value=exported) as browser,
        ):
            conversation = load(url, **options)
        self.assertEqual(conversation["source"]["provider"], "anthropic")
        self.assertEqual(len(conversation["messages"]), 2)
        browser.assert_called_once()

    def test_network_failure_does_not_launch_browser(self) -> None:
        url = "https://claude.ai/share/fixture"
        options = dict(timeout=1.0, browser="auto", browser_timeout=20.0)
        with (patch("panagent.api.fetch_share", side_effect=AcquisitionError("could not fetch share URL: timeout")),
              patch("panagent.api.fetch_share_browser") as browser):
            with self.assertRaisesRegex(AcquisitionError, "timeout"):
                load(url, **options)
        browser.assert_not_called()

    def test_cdp_uses_browser_without_plain_http(self) -> None:
        url = "https://claude.ai/share/fixture"
        options = dict(timeout=1.0, browser="auto", browser_timeout=20.0, cdp_url="http://127.0.0.1:9222")
        exported = (FIXTURES / "claude-share-export.json").read_text(encoding="utf-8")
        with (
            patch("panagent.api.fetch_share") as plain,
            patch("panagent.api.fetch_share_browser", return_value=exported) as browser,
        ):
            conversation = load(url, **options)
        self.assertEqual(len(conversation["messages"]), 2)
        plain.assert_not_called()
        browser.assert_called_once_with(url, timeout=20.0, mode="auto", cdp_url="http://127.0.0.1:9222", profile=None)
