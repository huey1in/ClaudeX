import json
import os
from threading import Lock

# 按文件路径分配锁，保证多线程并发写入同一账号文件时不冲突
_locks = {}
_locks_meta = Lock()


def _get_lock(filepath):
    with _locks_meta:
        if filepath not in _locks:
            _locks[filepath] = Lock()
        return _locks[filepath]


def load_accounts(filepath="accounts.json"):
    """读取账号文件，不存在或为空时返回空列表。"""
    if not os.path.exists(filepath):
        return []
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read().strip()
    if not content:
        return []
    return json.loads(content)


def save_account(account, filepath="accounts.json"):
    """将单个账号记录追加到账号文件（加锁，线程安全）。"""
    lock = _get_lock(filepath)
    with lock:
        records = load_accounts(filepath)
        records.append(account)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)


class AccountPool:
    """账号池：从账号文件加载记录，按轮询顺序取用（线程安全）。"""

    def __init__(self, filepath="accounts.json"):
        self._filepath = filepath
        self._lock = Lock()
        self._index = 0
        self.accounts = []
        self.reload()

    def reload(self):
        """重新从文件加载账号；文件为空则报错提示先注册。"""
        self.accounts = load_accounts(self._filepath)
        if not self.accounts:
            raise RuntimeError(f"{self._filepath} 为空，请先运行 register")
        print(f"[pool] 已加载 {len(self.accounts)} 个账号")

    def next(self):
        """按轮询顺序返回下一个账号。"""
        with self._lock:
            acct = self.accounts[self._index % len(self.accounts)]
            self._index += 1
        return acct

    def __len__(self):
        return len(self.accounts)
