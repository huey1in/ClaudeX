#!/usr/bin/env python3
"""
ClaudeX

用法:
  python main.py register [-n N] [-j J]
  python main.py check    [--accounts FILE]
"""
import argparse

from core.config import (
    REGISTER_COUNT, REGISTER_CONCURRENT,
    ACCOUNTS_FILE,
)
from core.console import print_log
from core.version import (
    VersionCheckError,
    __version__,
    fetch_remote_version,
    is_newer,
)


class VersionAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        print(f"本地版本: {__version__}")
        try:
            remote = fetch_remote_version()
        except VersionCheckError as exc:
            print(f"远端版本: 检查失败 ({exc})")
            parser.exit()

        remote_version = remote["version"]
        print(f"远端版本: {remote_version}")
        if is_newer(remote_version):
            print("发现新版本，更新内容:")
            for change in remote["changes"]:
                print(f"  - {change}")
        elif remote_version == __version__:
            print("当前已是最新版本。")
        else:
            print("本地版本高于远端版本。")
        parser.exit()


def cmd_register(args):
    from registration.register import register_batch

    subscription_failed = False
    subscribe = None
    if args.sepa:
        from billing.workflow import run_sepa_workflow

        def subscribe(account):
            nonlocal subscription_failed
            try:
                payments = run_sepa_workflow(
                    [account], accounts_file=args.accounts
                )
            except Exception as exc:
                subscription_failed = True
                print_log(
                    f"  [订阅失败] {account.get('email', account['uuid'])}: {exc}"
                )
            else:
                if any(payment.status == "failed" for payment in payments):
                    subscription_failed = True

    register_batch(
        count=args.count,
        concurrent=args.concurrent,
        accounts_file=args.accounts,
        on_success=subscribe,
    )
    return 1 if subscription_failed else 0


def cmd_check(args):
    from account.check import check_usage
    check_usage(accounts_file=args.accounts)
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog="claudex",
        description="ClaudeX -- claude.ai 账号批量注册工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py register -n 10 -j 3
  python main.py check
        """,
    )
    parser.add_argument(
        "--accounts", default=ACCOUNTS_FILE, metavar="FILE",
        help=f"账号文件路径 (默认: {ACCOUNTS_FILE})",
    )
    parser.add_argument(
        "--version", action=VersionAction, nargs=0,
        help="显示本地版本并检查 GitHub 远端版本",
    )

    sub = parser.add_subparsers(dest="command", metavar="命令")
    sub.required = True

    # register
    p_reg = sub.add_parser("register", aliases=["reg"], help="批量注册账号")
    p_reg.add_argument("-n", "--count", type=int, default=REGISTER_COUNT, metavar="N",
                       help=f"注册数量 (默认: {REGISTER_COUNT})")
    p_reg.add_argument("-j", "--concurrent", type=int, default=REGISTER_CONCURRENT,
                       metavar="J", help=f"并发数 (默认: {REGISTER_CONCURRENT})")
    p_reg.add_argument(
        "--sepa", action="store_true",
        help="每个账户注册成功后立即自动提交 SEPA Direct Debit",
    )
    p_reg.set_defaults(func=cmd_register)

    # check
    p_chk = sub.add_parser("check", help="查询所有账号用量")
    p_chk.set_defaults(func=cmd_check)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
