#!/usr/bin/env python3
"""
ClaudeX

用法:
  python main.py register [-n N] [-j J]
  python main.py check    [--accounts FILE]
"""
import argparse

from claudex.config import (
    REGISTER_COUNT, REGISTER_CONCURRENT,
    ACCOUNTS_FILE,
)


def cmd_register(args):
    from claudex.register import register_batch
    register_batch(count=args.count, concurrent=args.concurrent,
                   accounts_file=args.accounts)


def cmd_check(args):
    from claudex.check import check_usage
    check_usage(accounts_file=args.accounts)


def main():
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

    sub = parser.add_subparsers(dest="command", metavar="命令")
    sub.required = True

    # register
    p_reg = sub.add_parser("register", aliases=["reg"], help="批量注册账号")
    p_reg.add_argument("-n", "--count", type=int, default=REGISTER_COUNT, metavar="N",
                       help=f"注册数量 (默认: {REGISTER_COUNT})")
    p_reg.add_argument("-j", "--concurrent", type=int, default=REGISTER_CONCURRENT,
                       metavar="J", help=f"并发数 (默认: {REGISTER_CONCURRENT})")
    p_reg.set_defaults(func=cmd_register)

    # check
    p_chk = sub.add_parser("check", help="查询所有账号用量")
    p_chk.set_defaults(func=cmd_check)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
