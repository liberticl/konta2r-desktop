"""Cliente sync offline-first: register, totales, rename, reintento."""
from __future__ import annotations
import datetime
import threading
import requests


def build_direction_payload(events: list[dict]) -> dict:
    """HOOK futuro: agrega conteo por direccion cuando la API lo soporte.

    Por ahora POST /api/trafico/ solo acepta totales agregados
    (car_count, person_count, ...). Esta funcion queda lista para
    extender el payload sin tocar el loop de conteo.
    """
    by_dir: dict[str, dict[str, int]] = {}
    for e in events:
        d = e.get("direction") or "sin_linea"
        k = e.get("detected_key", "")
        by_dir.setdefault(d, {}).setdefault(k, 0)
        by_dir[d][k] += 1
    return {"by_direction": by_dir}


def totals_payload(totals: dict, when_iso: str | None = None) -> dict:
    when_iso = when_iso or datetime.datetime.now(
        datetime.timezone.utc).isoformat()
    return {
        "datetime": when_iso,
        "car_count": totals.get("car", 0),
        "person_count": totals.get("person", 0),
        "bicycle_count": totals.get("bicycle", 0),
        "motorcycle_count": totals.get("motorcycle", 0),
        "truck_count": totals.get("truck", 0),
        "bus_count": totals.get("bus", 0),
        "skater_count": totals.get("skater", 0),
        "pet_count": totals.get("pet", 0),
    }


class SyncClient:
    def __init__(self, api_base: str, store, cfg: dict,
                 on_status=None, timeout: int = 15):
        self.api = api_base.rstrip("/")
        self.store = store
        self.cfg = cfg
        self.on_status = on_status or (lambda ok, msg: None)
        self.timeout = timeout
        self._timer = None

    def _headers(self):
        tok = self.cfg.get("token", "")
        return {"Authorization": f"Bearer {tok}"} if tok else {}

    def online(self) -> bool:
        try:
            requests.head(self.api + "/", timeout=5)
            return True
        except requests.RequestException:
            return False

    def register(self, fingerprint: str, user_agent: str, coords: str = ""):
        r = requests.post(self.api + "/api/trafico/register/",
                          json={"fingerprint": fingerprint,
                                "user_agent": user_agent, "coords": coords},
                          timeout=self.timeout)
        r.raise_for_status()
        data = r.json()
        self.cfg["token"] = data.get("token", "")
        if data.get("device_name") and not self.cfg.get("device_name"):
            self.cfg["device_name"] = data["device_name"]
        self.on_status(True, "registrado")
        return data

    def rename(self, name: str):
        r = requests.patch(self.api + "/api/trafico/device/",
                           json={"name": name}, headers=self._headers(),
                           timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def flush(self) -> bool:
        """Envia agregados pendientes. Retorna True si quedo al dia."""
        totals = self.store.pending_totals()
        if sum(totals.values()) == 0:
            self.on_status(True, "al dia")
            return True
        payload = totals_payload(totals)
        # Hook direccion (aun no enviado; la API solo acepta totales):
        _future = build_direction_payload([])  # noqa: F841
        try:
            r = requests.post(self.api + "/api/trafico/", json=payload,
                              headers=self._headers(), timeout=self.timeout)
            r.raise_for_status()
        except requests.RequestException as exc:
            self.on_status(False, f"sin conexion: {exc.__class__.__name__}")
            self.schedule_retry()
            return False
        self.store.mark_synced(self.store.pending_ids())
        self.on_status(True, "sincronizado")
        return True

    def schedule_retry(self, interval_min: float = 1.0):
        self.cancel_retry()
        t = threading.Timer(interval_min * 60, self.flush)
        t.daemon = True
        self._timer = t
        t.start()

    def schedule_periodic(self, interval_min: float):
        self.cancel_retry()
        def _tick():
            self.flush()
            self.schedule_periodic(interval_min)
        t = threading.Timer(max(60.0, interval_min * 60), _tick)
        t.daemon = True
        self._timer = t
        t.start()

    def cancel_retry(self):
        if self._timer is not None:
            try:
                self._timer.cancel()
            except Exception:
                pass
            self._timer = None
