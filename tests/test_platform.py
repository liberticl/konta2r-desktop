"""Tests multiplataforma: lógica pura, sin cámara ni GUI."""
import os

from konta2r import platform as pf
from konta2r import settings as st


def test_raspberry_pi_from_device_tree(tmp_path):
    f = tmp_path / "model"
    f.write_bytes(b"\x00Raspberry Pi 4 Model B\x00")
    g = tmp_path / "other"
    g.write_bytes(b"Jetson Nano")
    if pf._OVERRIDE in ("auto", "", "linux"):
        assert pf.is_raspberry_pi(str(f)) is True
        assert pf.is_raspberry_pi(str(g)) is False
    assert pf.is_raspberry_pi("/no/existe") is (pf._OVERRIDE == "rpi")


def test_dirs_non_empty(monkeypatch):
    assert pf.config_dir()
    assert pf.media_dir()
    monkeypatch.setattr(pf, "IS_WINDOWS", True)
    monkeypatch.setenv("APPDATA", "/tmp/apptest")
    assert pf.config_dir() == "/tmp/apptest/konta2r"


def test_camera_strategy_and_probe(monkeypatch):
    monkeypatch.setattr(pf, "IS_WINDOWS", False)
    monkeypatch.setattr(pf, "IS_LINUX", True)
    assert pf.camera_name_strategy() == "v4l2"
    assert pf.camera_probe_max() == 10
    monkeypatch.setattr(pf, "IS_WINDOWS", True)
    monkeypatch.setattr(pf, "IS_LINUX", False)
    assert pf.camera_name_strategy() == "dshow"
    assert pf.camera_probe_max() == 6


def test_infer_threads_bounds():
    assert 1 <= pf.infer_threads() <= 4


def test_default_model_size(monkeypatch):
    monkeypatch.setattr(pf, "is_raspberry_pi", lambda *a, **k: True)
    assert st.default_model_size() == 320
    monkeypatch.setattr(pf, "is_raspberry_pi", lambda *a, **k: False)
    monkeypatch.setattr(pf, "total_ram_gb", lambda: 1.0)
    assert st.default_model_size() == 320
    monkeypatch.setattr(pf, "total_ram_gb", lambda: 16.0)
    assert st.default_model_size() == 640


def test_describe_and_ram():
    s = st.describe()
    assert "so=" in s and "hilos=" in s and "modelo_sugerido=" in s
    r = pf.total_ram_gb()
    assert r is None or r > 0


def test_dshow_names_without_dependency():
    assert isinstance(pf.dshow_device_names(), dict)


def test_store_side_columns(tmp_path):
    from konta2r.store import Store
    st = Store(path=str(tmp_path / "q.db"))
    st.save_event(detected_key="car", direction="A->B", side_a="N",
                  side_b="S", timestamp_iso="2026-01-01T00:00:00",
                  date="d", time="t")
    evs = st.pending_events()
    assert evs[0]["side_a"] == "N" and evs[0]["direction"] == "A->B"


def test_friendly_names_windows_safe(monkeypatch):
    from konta2r import capture
    monkeypatch.setattr(pf, "IS_WINDOWS", True)
    monkeypatch.setattr(pf, "IS_LINUX", False)
    # con monkeypatch de estrategia a dshow sin pygrabber -> {}
    assert capture._friendly_names() == {}
