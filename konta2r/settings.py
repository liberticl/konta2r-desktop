"""Variables globales: ÚNICO lugar de definición.

Regla: ningún otro módulo define rutas, defaults de config, timeouts de
red, tamaños de modelo, clases ni límites de texto. Todos importan desde
aquí (`from konta2r import settings as st`). A `platform.py` solo se le
preguntan hechos del SO (no guarda valores de la app).
"""
from __future__ import annotations

from konta2r import platform as pf

# Idioma y tema de la UI (códigos; textos en strings.py).
LANG_DEFAULT = "es"
THEMES = ("dark", "light", "system")
THEME_DEFAULT = "dark"

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
RECORD_EVERY_N_DEFAULT = 1  # grabar 1 de cada N frames
RECORD_EVERY_N_MAX = 10

# ---- Modelo / inferencia ----
MODEL_SIZES = (320, 640)
MODEL_DEFAULT = 320
MODEL_SWITCH_THRESHOLD = 480  # slider: >= esto usa el grande
RAM_SMALL_GB = 2.0  # hasta esto se sugiere el modelo chico
MODEL_FILES = {320: "yolo26n-320.onnx", 640: "yolo26n.onnx"}


def default_model_size() -> int:
    """Solo instalaciones nuevas: Pi o poca RAM -> chico."""
    if pf.is_raspberry_pi():
        return MODEL_SIZES[0]
    ram = pf.total_ram_gb()
    if ram is not None and ram <= RAM_SMALL_GB:
        return MODEL_SIZES[0]
    return MODEL_SIZES[1]


def describe() -> str:
    """Una línea para el log de inicio: entorno efectivo de la app."""
    ram = pf.total_ram_gb()
    ram_s = f"{ram:.1f}" if ram else "?"
    return (f"so={pf.SYSTEM} maq={pf.machine()} "
            f"rpi={pf.is_raspberry_pi()} ram_gb={ram_s} "
            f"hilos={pf.infer_threads()} modelo_sugerido={default_model_size()}")
CONF_DEFAULT = 0.50
CONF_MIN = 0.1
CONF_MAX = 0.9

# ---- Clases contables (keys internas + etiquetas UI) ----
CLASS_KEYS = ("person", "bicycle", "skater", "car",
              "motorcycle", "bus", "truck", "pet")
# Nombres visibles por idioma: strings.CLASS_NAMES (único lugar).

# ---- Sync / medición ----
SYNC_INTERVAL_DEFAULT = 1  # minutos entre envíos

# ---- Límites de texto (API: máx 100 lados, 200 nombre) ----
SIDE_NAME_MAX = 100
DEVICE_NAME_MAX = 200

# ---- Tracker (idéntico a la web; ms / frames / px) ----
TRACK_MAX_AGE_MS = 1500     # olvida tracks sin ver por más de esto
TRACK_MIN_STABLE = 3        # frames estables para contar por aparición
TRACK_COOLDOWN_MS = 1200    # anti-doble-conteo tras un cruce
TRACK_DEADZONE_PX = 12      # banda muerta sobre la línea
TRACK_MATCH_MIN_PX = 60     # distancia máx de asociación (piso)
TRACK_MATCH_MAX_PX = 180    # distancia máx de asociación (techo)
TRACK_MATCH_DIAG_FACTOR = 0.8  # techo = diagonal_bbox * factor
TRACK_IOU_WEIGHT = 80       # score = dist - IoU * peso

# ---- Debug local (solo sesión, no persistente) ----
DEBUG_HOST = "http://localhost"
DEBUG_PORT_DEFAULT = "8000"

# ---- Tema UI (único lugar para la estética; solo visual, sin lógica) ----
# Paleta sobria sobre el modo oscuro de CustomTkinter.
UI_PRIMARY = "#2563eb"   # acciones principales (Guardar, enlaces clave)
UI_START = "#16a34a"     # iniciar medición
UI_STOP = "#dc2626"      # finalizar / grabar activo
UI_WARN = "#ea580c"      # debug activo, avisos
UI_MUTED = "gray"        # textos secundarios y hints
UI_FONT = "Arial"        # fallback nativo si no hay otra
UI_TITLE = 13            # títulos de tarjetas
UI_SECTION = 12          # títulos de sección lateral
UI_BODY = 13             # texto normal (default CTk)
UI_SMALL = 11            # hints y notas
UI_VALUE = 16            # números de conteo
UI_CARD_RADIUS = 10      # esquinas de tarjetas
UI_CARD_BORDER = 1       # borde sutil de tarjetas
UI_BTN_H = 28            # alto estándar de botones
UI_BTN_HERO = 40         # alto del botón principal (medición/guardar)

# ---- Sesión ----
SESSION_PREFIX = "sesion_"
