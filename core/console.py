import builtins
import os
import re
import sys


_RESET = "\033[0m"
_RED = "\033[31m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_CYAN = "\033[36m"
_GRAY = "\033[90m"


def _enable_windows_ansi(stream):
    if os.name != "nt":
        return True
    try:
        import ctypes
        import msvcrt

        handle = msvcrt.get_osfhandle(stream.fileno())
        mode = ctypes.c_uint()
        kernel32 = ctypes.windll.kernel32
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        return bool(kernel32.SetConsoleMode(handle, mode.value | 0x0004))
    except (AttributeError, OSError, ValueError):
        return False


def color_enabled(stream=None):
    stream = stream or sys.stdout
    if "NO_COLOR" in os.environ or os.environ.get("TERM") == "dumb":
        return False
    if not getattr(stream, "isatty", lambda: False)():
        return False
    return _enable_windows_ansi(stream)


def _summary_color(message):
    if re.search(r"失败\s+[1-9]\d*", message):
        return _RED
    if re.search(r"[1-9]\d*\s+(?:失效|错误)", message):
        return _RED
    if re.search(r"待处理\s+[1-9]\d*", message):
        return _YELLOW
    return _GREEN


def _message_color(message):
    stripped = message.strip()
    if not stripped:
        return None
    if re.match(r"^\[(?:注册|订阅)\]\s*完成", stripped):
        return _summary_color(stripped)
    if stripped.startswith("汇总:"):
        return _summary_color(stripped)
    if any(marker in stripped for marker in (
        "[失败]", "[ERR]", "[EXPIRED]", "[订阅失败]",
    )):
        return _RED
    if "[成功]" in stripped:
        return _GREEN
    if any(marker in stripped for marker in (
        "[待处理]", "[重试", "等待", "提示:", "未找到账号",
    )):
        return _YELLOW
    if re.match(r"^\[\d+/\d+\]", stripped):
        return _CYAN
    if stripped.startswith(("[注册]", "[订阅]", "[pool]")):
        return _CYAN
    if message.startswith("    "):
        return _GRAY
    return None


def colorize_log(message, enabled=True):
    if not enabled:
        return message
    color = _message_color(message)
    if not color:
        return message
    return f"{color}{message}{_RESET}"


def print_log(*values, sep=" ", end="\n", file=None, flush=False):
    stream = file or sys.stdout
    message = sep.join(str(value) for value in values)
    rendered = colorize_log(message, enabled=color_enabled(stream))
    builtins.print(rendered, end=end, file=stream, flush=flush)
