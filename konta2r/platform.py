"""Plataforma (Ubuntu / Raspberry Pi OS / Windows): única fuente de verdad.

Todo lo que cambia entre SO vive acá: rutas, backend de cámara,
enumeración, hilos de inferencia, modelo por defecto, Tk y headless.

Para emular otra plataforma (CI/QEMU): KONTA2R_PLATFORM=linux|rpi|windows|mac.
"""
from __future__ import annotations
import ctypes
import os
import platform as _plat
import subprocess

APP_NAME = "konta2r"

# Tamaños de modelo ONNX disponibles (chico, grande).
MODEL_SIZES = (320, 640)

_OVERRIDE = os.environ.get("KONTA2R_PLATFORM", "auto").strip().lower()

_SYSTEM = _plat.system()  # Linux | Windows | Darwin | ...


def _resolve_system() -> str:
    if _OVERRIDE in ("linux", "windows", "mac", "darwin"):
        return {"mac": "Darwin"}.get(_OVERRIDE, _OVERRIDE.capitalize())
    if _OVERRIDE == "rpi":
        return "Linux"
    return _SYSTEM


SYSTEM = _resolve_system()
IS_WINDOWS = SYSTEM == "Windows"
IS_MAC = SYSTEM == "Darwin"
IS_LINUX = SYSTEM == "Linux"


def is_raspberry_pi(device_tree: str = "/proc/device-tree/model") -> bool:
    """True en Pi real. Con override KONTA2R_PLATFORM=rpi, True siempre."""
    if _OVERRIDE == "rpi":
        return True
    if not IS_LINUX:
        return False
    try:
        with open(device_tree, "rb") as fh:
            return b"Raspberry Pi" in fh.read(128)
    except OSError:
        return False


def total_ram_gb() -> float | None:
    """RAM total sin dependencias. None si no se puede saber."""
    try:
        if IS_LINUX:
            try:
                pages = os.sysconf("SC_PHYS_PAGES")
                page = os.sysconf("SC_PAGE_SIZE")
                if pages > 0 and page > 0:
                    return pages * page / 1e9
            except (ValueError, OSError):
                pass
            with open("/proc/meminfo", encoding="utf-8") as fh:
                for line in fh:
                    if line.startswith("MemTotal:"):
                        return int(line.split()[1]) / 1e6  # kB -> GB
        elif IS_WINDOWS:
            class _Mem(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong),
                             ("dwMemoryLoad", ctypes.c_ulong),
                             ("ullTotalPhys", ctypes.c_ulonglong),
                             ("ullAvailPhys", ctypes.c_ulonglong),
                             ("ullTotalPageFile", ctypes.c_ulonglong),
                             ("ullAvailPageFile", ctypes.c_ulonglong),
                             ("ullTotalVirtual", ctypes.c_ulonglong),
                             ("ullAvailVirtual", ctypes.c_ulonglong),
                             ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            st = _Mem()
            st.dwLength = ctypes.sizeof(_Mem)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
                return st.ullTotalPhys / 1e9
        elif IS_MAC:
            out = subprocess.run(["sysctl", "-n", "hw.memsize"],
                                 capture_output=True, text=True,
                                 timeout=5).stdout.strip()
            if out.isdigit():
                return int(out) / 1e9
    except Exception:  # noqa: BLE001
        pass
    return None


def config_dir() -> str:
    if IS_WINDOWS:
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, APP_NAME)
    if IS_MAC:
        return os.path.join(os.path.expanduser("~"), "Library",
                             "Application Support", APP_NAME)
    return os.path.join(os.path.expanduser("~"), ".config", APP_NAME)


def media_dir() -> str:
    """Fotos/videos/CSV: carpeta visible, fuera de roaming (Windows)."""
    return os.path.join(os.path.expanduser("~"), APP_NAME)


def camera_backend():
    """Backend OpenCV por SO. None = default. Import diferido (tests)."""
    try:
        import cv2
    except ImportError:
        return None
    if IS_WINDOWS:
        return getattr(cv2, "CAP_DSHOW", None)  # apertura rápida en Windows
    return None  # Linux/Pi: V4L2 por defecto


def camera_probe_max() -> int:
    """Cuántos índices probar. En Windows cada fallo MSMF tarda segundos."""
    return 6 if IS_WINDOWS else 10


def camera_name_strategy() -> str:
    """'v4l2' | 'dshow' | 'generic' según SO."""
    if IS_WINDOWS:
        return "dshow"
    if IS_LINUX:
        return "v4l2"
    return "generic"


def dshow_device_names() -> dict[int, str]:
    """Nombres amistosos en Windows vía pygrabber (opcional). {} si no está."""
    try:
        from pygrabber.dshow_graph import FilterGraph
        names = {}
        for i, name in enumerate(FilterGraph().get_input_devices()):
            names[i] = name
        return names
    except Exception:  # noqa: BLE001
        return {}


def infer_threads() -> int:
    n = os.cpu_count() or 4
    return max(1, min(n - 1, 4))


def default_model_size() -> int:
    """Solo para instalaciones nuevas: Pi o poca RAM -> chico."""
    if is_raspberry_pi():
        return MODEL_SIZES[0]
    ram = total_ram_gb()
    if ram is not None and ram <= 2.0:
        return MODEL_SIZES[0]
    return MODEL_SIZES[1]


def is_headless() -> bool:
    if IS_LINUX:
        return not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    return False


def tk_install_hint() -> str:
    if IS_WINDOWS:
        return "Reinstala Python marcando 'tcl/tk and IDLE'."
    if IS_MAC:
        return "Instala python.org (incluye Tcl/Tk) o: brew install python-tk."
    if is_raspberry_pi():
        return "En Raspberry Pi OS: sudo apt install python3-tk (o python3.X-tk según versión)."
    return ("Falta Tk: sudo apt install python3-tk. "
            "Con pyenv, instala libtk8.6-dev + libjpeg-dev y recompila: "
            "pyenv install <versión>.")


def describe() -> str:
    ram = total_ram_gb()
    ram_s = f"{ram:.1f}" if ram else "?"
    return (f"so={SYSTEM} maq={_plat.machine()} rpi={is_raspberry_pi()} "
            f"ram_gb={ram_s} hilos={infer_threads()} "
            f"modelo_sugerido={default_model_size()}")
