# konta2r-desktop

Port desktop (Python) del contador web con **camara local** (sin URL/HLS/archivo).

## Ejecutar
```bash
pip install -r requirements.txt
cp /home/francisco/andeschileong/andeschileong-v2/apps/mediciones/static/mediciones/models/*.onnx models/
python3 -m konta2r
```
Config: `~/.config/konta2r/config.json`. DB local: `~/.config/konta2r/queue.db`.

## API actual
- `POST /api/trafico/register/` auto-registro (fingerprint SHA256 maquina+coords).
- `POST /api/trafico/` solo **totales agregados** (sin direccion).
- `PATCH /api/trafico/device/` renombrar.
Cola offline-first: eventos SQLite con direccion; sync envia totales y reintenta con timer.

## Que falta para direccion en API
Ver seccion final del reporte (hook `build_direction_payload()` ya deja el payload listo).
