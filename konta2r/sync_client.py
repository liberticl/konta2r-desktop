"""Cliente sync offline-first: register, totales + dirección A/B, rename."""
from __future__ import annotations
import datetime
import threading
import requests

# interno tracker/store -> campo API
KEY_TO_API = {
    "car": "car_count",
    "person": "person_count",
    "bicycle": "bicycle_count",
    "motorcycle": "motorcycle_count",
    "truck": "truck_count",
    "bus": "bus_count",
    "skater": "skater_count",
    "pet": "pet_count",
}
API_TO_KEY = {v: k for k, v in KEY_TO_API.items()}


def _api_counts(internal: dict) -> dict:
    """Convierte {car,person,...} -> {car_count,...} solo con valores >0."""
    out = {}
    for k, v in (internal or {}).items():
        if k in KEY_TO_API and int(v or 0) > 0:
            out[KEY_TO_API[k]] = int(v)
    return out


def build_direction_payload(events: list[dict]) -> dict:
    """Arma direction_counts según contrato nuevo:
    {"a_to_b": {bicycle_count: 3}, "b_to_a": {bicycle_count: 1}}
    Eventos usan direction "A->B"/"B->A" y detected_key interno.
    """
    a_to_b: dict[str, int] = {}
    b_to_a: dict[str, int] = {}
    for e in events or []:
        d = (e.get("direction") or "").strip()
        key = e.get("detected_key", "")
        api_field = KEY_TO_API.get(key)
        if not api_field:
            continue
        if d == "A->B":
            a_to_b[api_field] = a_to_b.get(api_field, 0) + 1
        elif d == "B->A":
            b_to_a[api_field] = b_to_a.get(api_field, 0) + 1
    return {"a_to_b": a_to_b, "b_to_a": b_to_a}


def totals_payload(totals: dict, when_iso: str | None = None,
                   line: dict | None = None,
                   direction_counts: dict | None = None) -> dict:
    when_iso = when_iso or datetime.datetime.now(
        datetime.timezone.utc).isoformat()
    payload: dict = {"datetime": when_iso}
    payload.update(_api_counts(totals))
    # CON dirección: line + direction_counts (aunque vayan vacíos parciales)
    if line is not None:
        payload["line"] = {"x1": float(line["x1"]), "y1": float(line["y1"]),
                           "x2": float(line["x2"]), "y2": float(line["y2"])}
        dc = direction_counts or {"a_to_b": {}, "b_to_a": {}}
        payload["direction_counts"] = {
            "a_to_b": dict(dc.get("a_to_b", {})),
            "b_to_a": dict(dc.get("b_to_a", {})),
        }
    return payload


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
        # Eventos pendientes para totales + dirección
        try:
            events = self.store.pending_events()
        except AttributeError:
            events = []
        totals = self.store.pending_totals()
        if sum(totals.values()) == 0:
            self.on_status(True, "al dia")
            return True
        line = (self.cfg or {}).get("line")
        if line:
            direction_counts = build_direction_payload(events)
            # Consistencia: totales = suma direccional (si hay mezcla sin
            # dirección por conteo por aparición, igual se envían totales).
            payload = totals_payload(totals, line=line,
                                     direction_counts=direction_counts)
        else:
            # SIN dirección: backward-compatible, sin keys line/direction_counts
            payload = totals_payload(totals)
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
