import io
import unittest
from argparse import Namespace
from types import SimpleNamespace
from unittest.mock import patch

import main


class CliTests(unittest.TestCase):
    @patch("main.fetch_remote_version")
    def test_version_flag_reports_local_remote_and_changes(self, fetch_remote):
        fetch_remote.return_value = {
            "version": "0.3.0",
            "changes": ["新增更新检查", "完善版本信息"],
        }
        with patch("sys.stdout", new_callable=io.StringIO) as stdout:
            with self.assertRaises(SystemExit) as exit_context:
                main.build_parser().parse_args(["--version"])

        self.assertEqual(exit_context.exception.code, 0)
        self.assertEqual(
            stdout.getvalue(),
            "本地版本: 0.2.0\n"
            "远端版本: 0.3.0\n"
            "发现新版本，更新内容:\n"
            "  - 新增更新检查\n"
            "  - 完善版本信息\n",
        )

    @patch("main.fetch_remote_version")
    def test_version_flag_keeps_local_result_when_remote_check_fails(
        self, fetch_remote
    ):
        fetch_remote.side_effect = main.VersionCheckError("连接超时")

        with patch("sys.stdout", new_callable=io.StringIO) as stdout:
            with self.assertRaises(SystemExit) as exit_context:
                main.build_parser().parse_args(["--version"])

        self.assertEqual(exit_context.exception.code, 0)
        self.assertEqual(
            stdout.getvalue(),
            "本地版本: 0.2.0\n远端版本: 检查失败 (连接超时)\n",
        )

    def test_register_sepa_flag_is_opt_in(self):
        parser = main.build_parser()

        default_args = parser.parse_args(["register"])
        sepa_args = parser.parse_args(["register", "--sepa"])

        self.assertFalse(default_args.sepa)
        self.assertTrue(sepa_args.sepa)

    @patch("billing.workflow.run_sepa_workflow")
    @patch("registration.register.register_batch")
    def test_default_register_does_not_start_billing(self, register_batch, workflow):
        register_batch.return_value = [{"uuid": "one"}]
        args = Namespace(count=1, concurrent=1, accounts="accounts.json", sepa=False)

        result = main.cmd_register(args)

        self.assertEqual(result, 0)
        workflow.assert_not_called()

    @patch("billing.workflow.run_sepa_workflow")
    @patch("registration.register.register_batch")
    def test_sepa_runs_immediately_after_each_successful_registration(
            self, register_batch, workflow):
        accounts = [{"uuid": "one"}, {"uuid": "two"}]
        events = []

        def register_side_effect(**kwargs):
            for account in accounts:
                events.append(("registered", account["uuid"]))
                if kwargs.get("on_success"):
                    kwargs["on_success"](account)
            return accounts

        def workflow_side_effect(batch, accounts_file):
            events.append(("subscribed", [account["uuid"] for account in batch]))
            return [SimpleNamespace(status="succeeded")]

        register_batch.side_effect = register_side_effect
        workflow.side_effect = workflow_side_effect
        args = Namespace(count=2, concurrent=2, accounts="custom.json", sepa=True)

        result = main.cmd_register(args)

        self.assertEqual(result, 0)
        self.assertEqual(events, [
            ("registered", "one"),
            ("subscribed", ["one"]),
            ("registered", "two"),
            ("subscribed", ["two"]),
        ])

    @patch("billing.workflow.run_sepa_workflow")
    @patch("registration.register.register_batch")
    def test_sepa_returns_nonzero_when_protocol_failure_remains(
            self, register_batch, workflow):
        account = {"uuid": "one"}

        def register_side_effect(**kwargs):
            kwargs["on_success"](account)
            return [account]

        register_batch.side_effect = register_side_effect
        workflow.return_value = [SimpleNamespace(status="failed")]
        args = Namespace(count=1, concurrent=1, accounts="accounts.json", sepa=True)

        self.assertEqual(main.cmd_register(args), 1)


if __name__ == "__main__":
    unittest.main()
