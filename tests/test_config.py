import importlib
import os
import unittest
from unittest.mock import patch

from core import config


_LEGACY_HEADER_ENV = {
    "CLAUDE_BASE_URL": "https://sentinel.invalid",
    "CLAUDE_ACCEPT": "sentinel/accept",
    "CLAUDE_ACCEPT_LANGUAGE": "xx-SENTINEL",
    "CLAUDE_CLIENT_PLATFORM": "sentinel-platform",
    "CLAUDE_CLIENT_VERSION": "sentinel-version",
    "CLAUDE_CLIENT_SHA": "sentinel-sha",
    "CLAUDE_USER_AGENT": "sentinel-user-agent",
    "CLAUDE_ANONYMOUS_ID": "sentinel-anonymous-id",
    "CLAUDE_DEVICE_ID": "sentinel-device-id",
    "CLAUDE_RANDOMIZE_FINGERPRINT": "0",
}


class HeaderGenerationTests(unittest.TestCase):
    def tearDown(self):
        importlib.reload(config)

    def test_legacy_environment_variables_cannot_override_headers(self):
        with patch.dict(os.environ, _LEGACY_HEADER_ENV):
            importlib.reload(config)
            headers = config.build_headers("user@example.com")

        self.assertEqual(headers["accept"], "*/*")
        self.assertEqual(config.BASE_URL, "https://claude.ai")
        self.assertEqual(headers["origin"], "https://claude.ai")
        self.assertEqual(headers["referer"], "https://claude.ai/")
        self.assertNotEqual(headers["accept-language"], "xx-SENTINEL")
        self.assertEqual(headers["anthropic-client-platform"], "web_claude_ai")
        self.assertEqual(headers["anthropic-client-version"], "1.0.0")
        self.assertRegex(headers["anthropic-client-sha"], r"^[0-9a-f]{40}$")
        self.assertNotEqual(headers["user-agent"], "sentinel-user-agent")
        self.assertNotEqual(
            headers["anthropic-anonymous-id"], "sentinel-anonymous-id"
        )
        self.assertNotEqual(headers["anthropic-device-id"], "sentinel-device-id")

    def test_same_seed_produces_the_same_complete_header_profile(self):
        first = config.build_headers("same@example.com")
        second = config.build_headers("same@example.com")

        self.assertEqual(first, second)

    def test_different_seeds_produce_different_identity_headers(self):
        first = config.build_headers("one@example.com")
        second = config.build_headers("two@example.com")

        self.assertNotEqual(
            first["anthropic-anonymous-id"], second["anthropic-anonymous-id"]
        )
        self.assertNotEqual(
            first["anthropic-device-id"], second["anthropic-device-id"]
        )


if __name__ == "__main__":
    unittest.main()
