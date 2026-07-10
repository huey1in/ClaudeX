import requests
from .config import build_headers, PROXIES


def make_session(cookies=None, seed=None):
    s = requests.Session()
    s.headers.update(build_headers(seed))
    if PROXIES:
        s.proxies.update(PROXIES)
    if cookies:
        for k, v in cookies.items():
            s.cookies.set(k, v, domain="claude.ai")
    return s
