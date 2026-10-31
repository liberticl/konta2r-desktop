"""Captura con camara local (sin URL/HLS/archivo)."""
from __future__ import annotations
import cv2
import os
import re
import subprocess


def _friendly_names() -> dict[int, str]:
    """Índice -> nombre amigable. v4l2-ctl, luego sysfs, si no 'Cámara N'."""
    names: dict[int, str] = {}
    try:
        out = subprocess.run(["v4l2-ctl", "--list-devices"],
                             capture_output=True, text=True, timeout=5).stdout
        cur = ""
        for line in out.splitlines():
            if line and not line.startswith(("\t", " ")):
                cur = line.strip().rstrip(":").split("(")[0].strip() or cur
            m = re.search(r"/dev/video(\d+)", line)
            if m:
                idx = int(m.group(1))
                if idx not in names and cur:
                    names[idx] = cur
    except Exception:  # noqa: BLE001
        pass
    return names


def _sysfs_name(i: int) -> str:
    try:
        with open(f"/sys/class/video4linux/video{i}/name", encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return ""


def list_cameras(max_index: int = 10) -> list[tuple[int, str]]:
    """Solo disponibles: [(index, nombre)]. Prueba apertura real."""
    sys_names = _friendly_names()
    found: list[tuple[int, str]] = []
    for i in range(max_index):
        cap = cv2.VideoCapture(i)
        ok = cap.isOpened()
        cap.release()
        if ok:
            nm = sys_names.get(i) or _sysfs_name(i) or f"Cámara {i}"
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

    def open(self) -> bool:
        self.close()
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
