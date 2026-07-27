"""ClaudeX 本地及远端版本信息。"""

import json
import re
from pathlib import Path

import requests


REPOSITORY_URL = "https://github.com/huey1in/ClaudeX"
REMOTE_VERSION_URL = (
    "https://raw.githubusercontent.com/huey1in/ClaudeX/main/version.json"
)
_VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")


class VersionCheckError(RuntimeError):
    """远端版本信息无法安全读取。"""


def _validate_version_info(data):
    if not isinstance(data, dict):
        raise VersionCheckError("远端版本信息格式无效")

    version = data.get("version")
    changes = data.get("changes")
    if (
        not isinstance(version, str)
        or not _VERSION_PATTERN.fullmatch(version)
        or not isinstance(changes, list)
        or not all(isinstance(item, str) and item.strip() for item in changes)
    ):
        raise VersionCheckError("远端版本信息格式无效")

    return {
        "version": version,
        "changes": [item.strip() for item in changes],
    }


def _load_local_version():
    path = Path(__file__).resolve().parents[1] / "version.json"
    with path.open("r", encoding="utf-8") as file:
        return _validate_version_info(json.load(file))


LOCAL_VERSION_INFO = _load_local_version()
__version__ = LOCAL_VERSION_INFO["version"]


def fetch_remote_version(request=None):
    """从 GitHub main 分支读取并校验版本信息。"""
    requester = request or requests.get
    try:
        response = requester(REMOTE_VERSION_URL, timeout=10)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise VersionCheckError(str(exc) or "无法读取远端版本信息") from exc
    return _validate_version_info(data)


def is_newer(candidate, current=__version__):
    """比较 x.y.z 格式的版本号。"""
    if not _VERSION_PATTERN.fullmatch(candidate):
        raise VersionCheckError("远端版本信息格式无效")
    if not _VERSION_PATTERN.fullmatch(current):
        raise VersionCheckError("本地版本信息格式无效")
    return tuple(map(int, candidate.split("."))) > tuple(map(int, current.split(".")))
