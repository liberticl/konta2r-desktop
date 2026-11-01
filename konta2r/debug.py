"""Log de debug: archivo + buffer en memoria para la terminal UI."""
from __future__ import annotations
import collections
import datetime
import os

from konta2r import platform as pf

APP_DIR = pf.config_dir()
LOG_PATH = os.path.join(APP_DIR, "debug.log")

_buf: collections.deque[str] = collections.deque(maxlen=500)


def _ts() -> str:
    return datetime.datetime.now().strftime("%H:%M:%S")


def log(msg: str) -> str:
    line = f"[{_ts()}] {msg}"
    _buf.append(line)
    try:
        os.makedirs(APP_DIR, exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass
    return line


def snapshot() -> list[str]:
    return list(_buf)


def read_tail(n: int = 200) -> list[str]:
    try:
        with open(LOG_PATH, encoding="utf-8") as fh:
            lines = fh.readlines()
        return [l.rstrip("\n") for l in lines[-n:]]
    except OSError:
        return list(_buf)[-n:]
