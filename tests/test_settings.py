"""Variables globales: todo sale de settings.py (única definición).

Si agregas una ruta, default, timeout o límite nuevo, ponlo en
konta2r/settings.py y refréncialo. Estos tests lo exigen.
"""
import inspect
import pathlib

from konta2r import config_store, debug, infer, platform as pf
from konta2r import settings as st
from konta2r import store
from konta2r.capture import Camera
from konta2r.sync_client import SyncClient

ROOT = pathlib.Path(__file__).resolve().parent.parent / "konta2r"


def test_rutas_centralizadas():
    assert config_store.CONFIG_PATH == st.CONFIG_PATH
    assert config_store.APP_DIR == st.CONFIG_DIR
    assert store.DB_PATH == st.DB_PATH
    assert debug.LOG_PATH == st.LOG_PATH
    assert st.CONFIG_PATH.startswith(st.CONFIG_DIR)
    assert st.DB_PATH.startswith(st.CONFIG_DIR)


def test_defaults_centralizados():
    d = config_store.DEFAULTS
    assert d["width"] == st.CAMERA_WIDTH_DEFAULT
    assert d["height"] == st.CAMERA_HEIGHT_DEFAULT
    assert d["model_size"] == st.MODEL_DEFAULT
    assert d["conf_threshold"] == st.CONF_DEFAULT
    assert d["sync_interval_min"] == st.SYNC_INTERVAL_DEFAULT
    assert d["api_base"] == st.API_BASE_DEFAULT
    assert Camera().width == st.CAMERA_WIDTH_DEFAULT
    assert infer.parse_output0.__defaults__[0] == st.CONF_DEFAULT
    assert inspect.signature(SyncClient.__init__).parameters["timeout"].default == st.API_TIMEOUT
    assert inspect.signature(SyncClient.start_watcher).parameters["interval"].default == st.WATCHER_INTERVAL


def test_clases_centralizadas():
    assert tuple(infer.COUNT_KEYS) == tuple(st.CLASS_KEYS)
    from konta2r.ui import app as _  # noqa: F401  (solo si hay GUI)
    import konta2r.ui.app as ui
    assert tuple(ui.KEYS) == tuple(st.CLASS_KEYS)
    assert ui.LABELS == st.CLASS_LABELS


def test_sin_literales_duplicados():
    """Nadie repite rutas ni URL base: solo settings.py los define."""
    for f in ROOT.glob("*.py"):
        if f.name in ("settings.py", "platform.py"):
            continue
        src = f.read_text(encoding="utf-8")
        assert "~/.config" not in src, f"{f.name} reconstruye la ruta"
        assert '"https://andeschileong.cl"' not in src, f"{f.name} repite la URL"
    for f in (ROOT / "ui").glob("*.py"):
        src = f.read_text(encoding="utf-8")
        assert "~/.config" not in src, f"ui/{f.name} reconstruye la ruta"
        assert '"https://andeschileong.cl"' not in src, f"ui/{f.name} repite la URL"
