"""Geocodificación gratuita vía Nominatim (OpenStreetMap).

Política pública: 1 req/seg, User-Agent válido, sin bulk.
Mismo proveedor que usa el backend Django para reverse_geocode.
"""
from __future__ import annotations

import time

import requests

_URL = "https://nominatim.openstreetmap.org/search"
_UA = "konta2r-desktop/1.0 (contacto@andeschileong.cl)"
_last_call = 0.0


def forward(address: str, timeout: int = 10) -> tuple[str, str, str]:
    """Dirección -> (lat, lon, display_name). Lanza RuntimeError si falla."""
    global _last_call
    q = (address or "").strip()
    if not q:
        raise RuntimeError("dirección vacía")
    # respeta 1 req/seg
    dt = time.time() - _last_call
    if dt < 1.1:
        time.sleep(1.1 - dt)
    r = requests.get(_URL, params={"format": "jsonv2", "limit": 1, "q": q},
                     headers={"User-Agent": _UA}, timeout=timeout)
    _last_call = time.time()
    if r.status_code != 200:
        raise RuntimeError(f"Nominatim HTTP {r.status_code}")
    data = r.json()
    if not data:
        raise RuntimeError("sin resultados")
    it = data[0]
    return (str(it.get("lat", "")), str(it.get("lon", "")),
            str(it.get("display_name", "")))
