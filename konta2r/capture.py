"""Captura con camara local (nombres y backend según SO vía platform)."""
from __future__ import annotations
import cv2
import os
import re
import subprocess

from konta2r import platform as pf


def _v4l2_names() -> dict[int, str]:
    """v4l2-ctl --list-devices (solo Linux). {} si no existe/falla."""
    names: dict[int, str] = {}
    if pf.camera_name_strategy() != "v4l2":
        return names
    try:
        out = subprocess.run(["v4l2-ctl", "--list-devices"],
                             capture_output=True, text=True, timeout=5).stdout
    except Exception:  # noqa: BLE001  (incluye FileNotFoundError en Win)
        return names
    cur = ""
    for line in out.splitlines():
        if line and not line.startswith(("\t", " ")):
            cur = line.strip().rstrip(":").split("(")[0].strip() or cur
        m = re.search(r"/dev/video(\d+)", line)
        if m:
            idx = int(m.group(1))
            if idx not in names and cur:
                names[idx] = cur
    return names


def _friendly_names() -> dict[int, str]:
    """Nombres según estrategia de la plataforma (v4l2/dshow/genérico)."""
    strategy = pf.camera_name_strategy()
    if strategy == "v4l2":
        return _v4l2_names()
    if strategy == "dshow":
        return pf.dshow_device_names()
    return {}


def _sysfs_name(i: int) -> str:
    try:
        with open(f"/sys/class/video4linux/video{i}/name", encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return ""


def _device_key(i: int, name: str) -> str | None:
    """Agrupa nodos asociados a la misma cámara (video + metadata comparten device)."""
    if "metadata" in (name or "").lower():
        return f"meta:{i}"
    try:
        dev = os.path.realpath(f"/sys/class/video4linux/video{i}/device")
        if dev and "video4linux" not in dev:
            return f"{dev}|{name}"
    except OSError:
        pass
    return None


def list_cameras(max_index: int | None = None) -> list[tuple[int, str]]:
    """Solo disponibles, UNA entrada por cámara física.

    Cada cámara suele exponer 2 nodos /dev/video (captura + metadata)
    con el mismo nombre; se conserva solo el primero de cada grupo.
    """
    if max_index is None:
        max_index = pf.camera_probe_max()
    backend = pf.camera_backend()
    sys_names = _friendly_names()
    candidates: list[tuple[int, str]] = []
    for i in range(max_index):
        cap = cv2.VideoCapture(i, backend) if backend is not None else cv2.VideoCapture(i)
        ok = cap.isOpened()
        cap.release()
        if ok:
            nm = sys_names.get(i) or _sysfs_name(i) or f"Cámara {i}"
            candidates.append((i, nm))
    # dedup por dispositivo físico (solo cuando hay sysfs; sin eso se
    # conservan todas para no ocultar una cámara real)
    seen: set[str] = set()
    found: list[tuple[int, str]] = []
    for i, nm in candidates:
        key = _device_key(i, nm)
        if key is None:
            found.append((i, nm))
        elif key not in seen:
            seen.add(key)
            found.append((i, nm))
    return found


def camera_label(index: int, name: str) -> str:
    short = re.sub(r"\s+", " ", name or "").strip()[:40] or f"Cámara {index}"
    return f"{index} · {short}"


def label_to_index(label: str) -> int | None:
    m = re.match(r"\s*(\d+)", label or "")
    return int(m.group(1)) if m else None


def enumerate_cameras(max_index: int = 10):
    """Compat: solo índices disponibles."""
    return [i for i, _ in list_cameras(max_index)]


class Camera:
    def __init__(self, index: int = 0, width: int = 1280, height: int = 720):
        self.index = index
        self.width = width
        self.height = height
        self.cap = None
        self.backend = pf.camera_backend()

    def open(self) -> bool:
        self.close()
        if self.backend is not None:
            self.cap = cv2.VideoCapture(self.index, self.backend)
        else:
            self.cap = cv2.VideoCapture(self.index)
        if not self.cap.isOpened():
            return False
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        return True

    def read(self):
        if self.cap is None:
            return False, None
        return self.cap.read()

    def actual_size(self):
        if self.cap is None:
            return (0, 0)
        w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        return (w, h)

    def close(self):
        try:
            if self.cap is not None:
                self.cap.release()
        finally:
            self.cap = None
