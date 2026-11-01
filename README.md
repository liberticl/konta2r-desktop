# konta2r-desktop

Port desktop (Python) del contador web con **camara local** (sin URL/HLS/archivo).

## Ejecutar
```bash
pip install -r requirements.txt
cp /home/francisco/andeschileong/andeschileong-v2/apps/mediciones/static/mediciones/models/*.onnx models/
python3 -m konta2r
```
Config: Linux `~/.config/konta2r/config.json`, Windows `%APPDATA%/konta2r`. DB y log en la misma carpeta. Fotos/videos/CSV en `~/konta2r/`.

## Plataformas (módulo `konta2r/platform.py`)

| Tema | Ubuntu | Raspberry Pi OS | Windows |
|---|---|---|---|
| Cámara | V4L2, nombres vía `v4l2-ctl`/sysfs | Igual que Ubuntu | DirectShow, nombres genéricos (`pygrabber` opcional para nombres) |
| Enumeración | prueba índices 0-9 | igual | 0-5 (cada fallo MSMF es lento) + `CAP_DSHOW` |
| Modelo inicial | 640px (RAM>2GB) | 320px siempre | 640px (RAM>2GB) |
| Inferencia | CPU, máx 4 hilos | CPU, máx 4 hilos | CPU, máx 4 hilos |
| Tkinter | `sudo apt install python3-tk` (con pyenv: `libtk8.6-dev` y recompilar) | `sudo apt install python3-tk` | incluido en python.org |
| Sin pantalla | error claro (usa escritorio o X-forwarding) | igual (Lite no corre GUI) | n/a |

Todo el `print`/estado UI corre en el hilo de Tk (`after`); el watcher de red es 1 hebra + 1 socket cada 20s. Para emular otra plataforma: `KONTA2R_PLATFORM=linux|rpi|windows`.

## API actual
- `POST /api/trafico/register/` auto-registro (fingerprint SHA256 maquina+coords).
- `POST /api/trafico/` solo **totales agregados** (sin direccion).
- `PATCH /api/trafico/device/` renombrar.
Cola offline-first: eventos SQLite con direccion; sync envia totales y reintenta con timer.

## Que falta para direccion en API
Ver seccion final del reporte (hook `build_direction_payload()` ya deja el payload listo).
