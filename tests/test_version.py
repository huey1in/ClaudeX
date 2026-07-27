import unittest
from unittest.mock import Mock

from core.version import VersionCheckError, fetch_remote_version, is_newer


class VersionTests(unittest.TestCase):
    def test_fetches_and_validates_remote_version_info(self):
        response = Mock()
        response.json.return_value = {
            "version": "0.3.0",
            "changes": ["新增更新检查"],
        }
        request = Mock(return_value=response)

        info = fetch_remote_version(request=request)

        response.raise_for_status.assert_called_once_with()
        self.assertEqual(info["version"], "0.3.0")
        self.assertEqual(info["changes"], ["新增更新检查"])

    def test_rejects_invalid_remote_version_info(self):
        response = Mock()
        response.json.return_value = {
            "version": "next",
            "changes": "not-a-list",
        }

        with self.assertRaisesRegex(VersionCheckError, "格式无效"):
            fetch_remote_version(request=Mock(return_value=response))

    def test_compares_semantic_versions(self):
        self.assertTrue(is_newer("0.3.0", "0.2.0"))
        self.assertFalse(is_newer("0.2.0", "0.2.0"))
        self.assertFalse(is_newer("0.1.9", "0.2.0"))


if __name__ == "__main__":
    unittest.main()
