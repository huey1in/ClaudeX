import io
import os
import unittest
from unittest.mock import patch


class FakeTTY(io.StringIO):
    def isatty(self):
        return True


class ConsoleTests(unittest.TestCase):
    def test_applies_semantic_colors(self):
        from core.console import colorize_log

        cases = [
            ("  [1/7] 检查出口 IP…", "\033[36m"),
            ("  [成功] 注册完成", "\033[32m"),
            ("  [待处理] 等待结果", "\033[33m"),
            ("  [失败] 注册失败", "\033[31m"),
            ("        邮箱: test@example.com", "\033[90m"),
        ]
        for message, color in cases:
            with self.subTest(message=message):
                rendered = colorize_log(message, enabled=True)
                self.assertTrue(rendered.startswith(color))
                self.assertTrue(rendered.endswith("\033[0m"))
                self.assertIn(message, rendered)

    def test_summary_color_reflects_failures(self):
        from core.console import colorize_log

        success = colorize_log(
            "[注册] 完成: 成功 2 个，失败 0 个", enabled=True
        )
        failure = colorize_log(
            "[订阅] 完成: 成功 1 个，待处理 0 个，失败 1 个",
            enabled=True,
        )

        self.assertTrue(success.startswith("\033[32m"))
        self.assertTrue(failure.startswith("\033[31m"))

    def test_disabled_color_returns_plain_text(self):
        from core.console import colorize_log

        message = "  [成功] 注册完成"
        self.assertEqual(colorize_log(message, enabled=False), message)

    def test_no_color_disables_terminal_colors(self):
        from core.console import color_enabled

        with patch.dict(os.environ, {"NO_COLOR": "1"}):
            self.assertFalse(color_enabled(FakeTTY()))

    def test_redirected_output_stays_plain(self):
        from core.console import print_log

        output = io.StringIO()
        print_log("  [成功] 注册完成", file=output)

        self.assertEqual(output.getvalue(), "  [成功] 注册完成\n")


if __name__ == "__main__":
    unittest.main()
