"""Variables globales: ÚNICO lugar de definición.

Regla: ningún otro módulo define rutas, defaults de config, timeouts de
red, tamaños de modelo, clases ni límites de texto. Todos importan desde
aquí (`from konta2r import settings as st`). Lo que depende del SO vive
en `platform.py`; aquí solo se reunifican los valores de la app.
"""
from __future__ import annotations

from konta2r import platform as pf

# ---- Rutas (derivan de platform; no reconstruir os.path en cada módulo) ----
CONFIG_DIR = pf.config_dir()
CONFIG_PATH = f"{CONFIG_DIR}/config.json"
DB_PATH = f"{CONFIG_DIR}/queue.db"
LOG_PATH = f"{CONFIG_DIR}/debug.log"
MEDIA_DIR = pf.media_dir()

# ---- API ----
API_BASE_DEFAULT = "https://andeschileong.cl"
API_HOST_FALLBACK = "andeschileong.cl"
API_TIMEOUT = 15            # requests en register/device/flush
PROBE_TIMEOUT = 4           # TCP connect del watcher de red
ONLINE_TIMEOUT = 5          # HEAD / de online()
WATCHER_INTERVAL = 20.0     # chequeo caída/reconexión (segundos)
SYNC_MIN_INTERVAL_S = 60.0  # piso del timer periódico (aunque pidan menos)

# ---- Cámara ----
CAMERA_WIDTH_DEFAULT = 1280
CAMERA_HEIGHT_DEFAULT = 720
DISPLAY_W_DEFAULT = 760
DISPLAY_H_DEFAULT = 520
RECORD_FOURCC = "mp4v"
RECORD_FPS = 20.0

# ---- Modelo / inferencia ----
MODEL_SIZES = pf.MODEL_SIZES
MODEL_DEFAULT = 320
# OJO: el de 640 no lleva sufijo en el nombre del archivo.
MODEL_FILES = {320: "yolo26n-320.onnx", 640: "yolo26n.onnx"}
MODEL_SWITCH_THRESHOLD = 480  # slider: >= esto usa el grande
CONF_DEFAULT = 0.50
CONF_MIN = 0.1
CONF_MAX = 0.9

# ---- Clases contables (keys internas + etiquetas UI) ----
CLASS_KEYS = ("person", "bicycle", "skater", "car",
              "motorcycle", "bus", "truck", "pet")
CLASS_LABELS = {"person": "Peatones", "bicycle": "Bicis",
                "skater": "Patinetas", "car": "Autos",
                "motorcycle": "Motos", "bus": "Buses",
                "truck": "Camiones", "pet": "Mascotas"}

# ---- Sync / medición ----
SYNC_INTERVAL_DEFAULT = 5  # minutos entre envíos

# ---- Límites de texto (API: máx 100 lados, 200 nombre) ----
SIDE_NAME_MAX = 100
DEVICE_NAME_MAX = 200

# ---- Debug local (solo sesión, no persistente) ----
DEBUG_HOST = "http://localhost"
DEBUG_PORT_DEFAULT = "8000"

# ---- Sesión ----
SESSION_PREFIX = "sesion_"
