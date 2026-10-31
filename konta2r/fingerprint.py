"""Fingerprint estable: SHA256(machine-id + coords). Sin navegador."""
from __future__ import annotations
import hashlib
import os
import platform
import uuid


def _machine_id() -> str:
    for path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                val = fh.read().strip()
                if val:
                    return val
        except OSError:
            continue
    # fallback: MAC + hostname + usuario (estable por maquina)
    return f"{uuid.getnode():012x}-{platform.node()}-{os.path.expanduser('~')}"


def fingerprint(coords: str = "") -> str:
    raw = f"{_machine_id()}|{platform.system()}|{(coords or '').strip()}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def user_agent() -> str:
    return f"konta2r-desktop/{platform.system()}/{platform.machine()} python"
