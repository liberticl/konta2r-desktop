"""Config persistente (ruta y defaults desde settings)."""
from __future__ import annotations
import json
import os
from copy import deepcopy

from konta2r import settings as st

APP_DIR = st.CONFIG_DIR
CONFIG_PATH = st.CONFIG_PATH

CLASES_DEFAULT = {
    "person": True, "bicycle": True, "skater": True, "car": True,
    "motorcycle": True, "bus": True, "truck": True, "pet": True,
}

DEFAULTS = {
    "camera_index": 0,
    "width": st.CAMERA_WIDTH_DEFAULT,
    "height": st.CAMERA_HEIGHT_DEFAULT,
    "model_size": st.MODEL_DEFAULT,
    "conf_threshold": st.CONF_DEFAULT,
    "sync_interval_min": st.SYNC_INTERVAL_DEFAULT,
    "record_every_n": st.RECORD_EVERY_N_DEFAULT,
    "clases_activas": dict(CLASES_DEFAULT),
    "line": None,               # {"x1":..,"y1":..,"x2":..,"y2":..} norm o None
    "line_persistent": True,    # False = la línea vive solo esta sesión
    "side_a": "",               # nombre lado A (máx 100, ref)
    "side_b": "",               # nombre lado B (máx 100, ref)
    "device_name": "",
    "coords": "",               # "lat,lon"
    "api_base": st.API_BASE_DEFAULT,
    "token": "",
    "fingerprint": "",
    "lang": st.LANG_DEFAULT,
    "theme": st.THEME_DEFAULT,
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
