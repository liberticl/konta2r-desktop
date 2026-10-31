"""Preprocess: cover-resize (recorte central) a SxS + RGB 0-1 NCHW float32.

Replica contador.html: scale = max(S/sw, S/sh), dibujo centrado en
canvas SxS (lo que sobresale se recorta). Retorna tensor + meta para
mapear cajas del modelo a coordenadas del frame original.
"""
from __future__ import annotations
import numpy as np

try:
    import cv2
except ImportError:  # tests sin cv2: fallback numpy nearest
    cv2 = None


def cover_transform(src_w: int, src_h: int, size: int) -> dict:
    scale = max(size / max(1, src_w), size / max(1, src_h))
    rw, rh = src_w * scale, src_h * scale
    ox, oy = (size - rw) / 2.0, (size - rh) / 2.0
    return {"scale": scale, "offset_x": ox, "offset_y": oy,
            "rendered_w": rw, "rendered_h": rh}


def preprocess(frame_bgr: np.ndarray, size: int = 320):
    """frame_bgr: HxWx3 uint8 BGR. Retorna (tensor (1,3,S,S) float32, meta)."""
    if frame_bgr is None or frame_bgr.ndim != 3 or frame_bgr.shape[2] != 3:
        raise ValueError("frame BGR HxWx3 requerido")
    src_h, src_w = frame_bgr.shape[:2]
    meta = {"src_w": src_w, "src_h": src_h, "size": size,
            **cover_transform(src_w, src_h, size)}
    scale, ox, oy = meta["scale"], meta["offset_x"], meta["offset_y"]
    rw, rh = int(round(src_w * scale)), int(round(src_h * scale))
    if cv2 is not None:
        resized = cv2.resize(frame_bgr, (rw, rh), interpolation=cv2.INTER_LINEAR)
    else:  # fallback simple (solo tests)
        resized = np.repeat(np.repeat(frame_bgr,
                             max(1, rh // max(1, src_h)), axis=0),
                             max(1, rw // max(1, src_w)), axis=1)[:rh, :rw]
    canvas = np.zeros((size, size, 3), dtype=np.uint8)
    # destino en canvas
    dx0, dy0 = int(round(ox)), int(round(oy))
    sx0, sy0 = max(0, -dx0), max(0, -dy0)
    dx0c, dy0c = max(0, dx0), max(0, dy0)
    w = min(rw - sx0, size - dx0c)
    h = min(rh - sy0, size - dy0c)
    if w > 0 and h > 0:
        canvas[dy0c:dy0c + h, dx0c:dx0c + w] = resized[sy0:sy0 + h, sx0:sx0 + w]
    rgb = canvas[:, :, ::-1].astype(np.float32) / 255.0
    tensor = np.transpose(rgb, (2, 0, 1))[None, ...].astype(np.float32)
    return np.ascontiguousarray(tensor), meta


def model_box_to_src(box, meta: dict):
    """Caja [x1,y1,x2,y2] en coords modelo (0..S) -> coords frame original."""
    s, ox, oy = meta["scale"], meta["offset_x"], meta["offset_y"]
    x1, y1, x2, y2 = box
    return [(x1 - ox) / s, (y1 - oy) / s, (x2 - ox) / s, (y2 - oy) / s]


def src_to_display(box_src, src_w: int, src_h: int, disp_w: int, disp_h: int):
    """Cover-mapping frame original -> superficie de display (igual que web)."""
    t = cover_transform(src_w, src_h, 1)  # solo escala base
    # reutiliza logica cover generica
    scale = max(disp_w / max(1, src_w), disp_h / max(1, src_h))
    ox = (disp_w - src_w * scale) / 2.0
    oy = (disp_h - src_h * scale) / 2.0
    x1, y1, x2, y2 = box_src
    return [x1 * scale + ox, y1 * scale + oy,
            (x2 - x1) * scale, (y2 - y1) * scale]  # x,y,w,h display
