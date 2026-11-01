"""Config persistente (ruta según SO vía platform)."""
from __future__ import annotations
import json
import os
from copy import deepcopy

from konta2r import platform as pf

APP_DIR = pf.config_dir()
CONFIG_PATH = os.path.join(APP_DIR, "config.json")

CLASES_DEFAULT = {
    "person": True, "bicycle": True, "skater": True, "car": True,
    "motorcycle": True, "bus": True, "truck": True, "pet": True,
}

DEFAULTS = {
    "camera_index": 0,
    "width": 1280,
    "height": 720,
    "model_size": 320,          # 320 | 640
    "conf_threshold": 0.50,
    "sync_interval_min": 5,
    "clases_activas": dict(CLASES_DEFAULT),
    "line": None,               # {"x1":..,"y1":..,"x2":..,"y2":..} norm o None
    "line_persistent": True,    # False = la línea vive solo esta sesión
    "side_a": "",               # nombre lado A (máx 100, ref)
    "side_b": "",               # nombre lado B (máx 100, ref)
    "device_name": "",
    "coords": "",               # "lat,lon"
    "api_base": "https://andeschileong.cl",
    "token": "",
    "fingerprint": "",
}


def _merge(base: dict, override: dict) -> dict:
    out = deepcopy(base)
    for k, v in (override or {}).items():
        if k == "clases_activas" and isinstance(v, dict):
            merged = dict(CLASES_DEFAULT)
            merged.update({kk: bool(vv) for kk, vv in v.items() if kk in CLASES_DEFAULT})
            out[k] = merged
        elif k in out:
            out[k] = v
    return out


def load() -> dict:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return _merge(DEFAULTS, data if isinstance(data, dict) else {})
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return deepcopy(DEFAULTS)


def save(cfg: dict) -> str:
    os.makedirs(APP_DIR, exist_ok=True)
    # solo guarda claves conocidas
    clean = {k: cfg.get(k, DEFAULTS[k]) for k in DEFAULTS}
    with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
        json.dump(clean, fh, indent=2, ensure_ascii=False)
    return CONFIG_PATH
