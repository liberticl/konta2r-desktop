"""Cliente sync offline-first: register, 1 POST por evento, watcher de red."""
from __future__ import annotations
import datetime
import socket
import threading
import urllib.parse
import requests

from konta2r import debug as dbg

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
                   direction_counts: dict | None = None,
                   side_names: dict | None = None) -> dict:
    """Arma payload según docs/api.md.

    - Sin dirección: solo totales (>0) + datetime (line=None).
    - Con dirección: line obligatoria + direction_counts consistentes;
      por categoría total == A→B + B→A (si no cuadra, se omite esa
      categoría del desglose para no provocar 400, como la web).
    - side_names opcional {a,b} máx 100.
    """
    when_iso = when_iso or datetime.datetime.now(
        datetime.timezone.utc).isoformat()
    payload: dict = {"datetime": when_iso}
    payload.update(_api_counts(totals))
    if line is not None:
        ok_line = all(isinstance(line.get(k), (int, float)) and 0 <= line[k] <= 1
                      for k in ("x1", "y1", "x2", "y2"))
        if not ok_line:
            return payload
        payload["line"] = {"x1": float(line["x1"]), "y1": float(line["y1"]),
                           "x2": float(line["x2"]), "y2": float(line["y2"])}
        dc = direction_counts or {"a_to_b": {}, "b_to_a": {}}
        clean = {"a_to_b": {}, "b_to_a": {}}
        for api_field, total_v in list(payload.items()):
            if not api_field.endswith("_count") or api_field == "datetime":
                continue
            a = int((dc.get("a_to_b") or {}).get(api_field, 0) or 0)
            b = int((dc.get("b_to_a") or {}).get(api_field, 0) or 0)
            if a + b > 0 and a + b == int(total_v):
                if a > 0:
                    clean["a_to_b"][api_field] = a
                if b > 0:
                    clean["b_to_a"][api_field] = b
            # si d>0 pero != total: se omite (línea redibujada/pendientes viejos)
        if clean["a_to_b"] or clean["b_to_a"]:
            payload["direction_counts"] = clean
        a = (side_names or {}).get("a", "")[:100]
        b = (side_names or {}).get("b", "")[:100]
        if a or b:
            payload["side_names"] = {"a": a, "b": b}
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
        # watcher de red: una hebra durmiendo, 1 socket por chequeo
        self._online = True  # se corrige en el primer flush/probe
        self._watcher = None
        self._watch_stop = None
        self.on_change = None  # callback(bool online)

    def _probe(self) -> bool:
        """Chequeo barato: TCP connect al host de la API (sin TLS/HTTP)."""
        try:
            u = urllib.parse.urlparse(self.api)
            host = u.hostname or "andeschileong.cl"
            port = u.port or (443 if u.scheme == "https" else 80)
            with socket.create_connection((host, port), timeout=4):
                pass
            return True
        except OSError:
            return False

    def start_watcher(self, interval: float = 20.0, on_change=None):
        """Detecta caída/reconexión con uso mínimo (1 hebra + 1 socket c/20s).

        Al reconectar dispara flush() solo. No genera errores: si no hay
        red, flush() se omite en silencio hasta volver.
        """
        self.stop_watcher()
        if on_change is not None:
            self.on_change = on_change
        stop = threading.Event()
        self._watch_stop = stop

        def _loop():
            while not stop.wait(interval):
                try:
                    ok = self._probe()
                except Exception:  # noqa: BLE001
                    ok = False
                if ok != self._online:
                    self._online = ok
                    if ok:
                        dbg.log("red: reconexión detectada → enviando pendientes")
                        try:
                            if self.on_change:
                                self.on_change(True)
                            self.flush()
                        except Exception as exc:  # noqa: BLE001
                            dbg.log(f"flush tras reconexión falló: {exc}")
                    else:
                        dbg.log("red: caída detectada → se pausa el envío (sin errores)")
                        try:
                            if self.on_change:
                                self.on_change(False)
                        except Exception:  # noqa: BLE001
                            pass
        t = threading.Thread(target=_loop, daemon=True, name="net-watcher")
        self._watcher = t
        t.start()

    def stop_watcher(self):
        if self._watch_stop is not None:
            try:
                self._watch_stop.set()
            except Exception:  # noqa: BLE001
                pass
            self._watch_stop = None
        self._watcher = None

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
        dbg.log(f"API register {self.api}/api/trafico/register/ fp={fingerprint[:12]}…")
        r = requests.post(self.api + "/api/trafico/register/",
                          json={"fingerprint": fingerprint,
                                "user_agent": user_agent, "coords": coords},
                          timeout=self.timeout)
        r.raise_for_status()
        data = r.json()
        self.cfg["token"] = data.get("token", "")
        if data.get("device_name") and not self.cfg.get("device_name"):
            self.cfg["device_name"] = data["device_name"]
        dbg.log(f"API register OK device={data.get('device_name')} id={data.get('device_id')}")
        self.on_status(True, "registrado")
        return data

    def rename(self, name: str):
        dbg.log(f"API PATCH device nombre={name!r}")
        r = requests.patch(self.api + "/api/trafico/device/",
                           json={"name": name}, headers=self._headers(),
                           timeout=self.timeout)
        r.raise_for_status()
        dbg.log("API rename OK")
        return r.json()

    def _event_payload(self, ev: dict) -> dict:
        """Un registro único por evento, con su datetime real de creación."""
        key = ev.get("detected_key", "")
        totals = {key: 1} if key else {}
        when = ev.get("timestamp_iso") or None
        direction = (ev.get("direction") or "").strip()
        line = (self.cfg or {}).get("line")
        if direction in ("A->B", "B->A") and line:
            api_field = KEY_TO_API.get(key)
            dc = {"a_to_b": {}, "b_to_a": {}}
            if api_field:
                if direction == "A->B":
                    dc["a_to_b"][api_field] = 1
                else:
                    dc["b_to_a"][api_field] = 1
            sides = {"a": (self.cfg or {}).get("side_a", ""),
                     "b": (self.cfg or {}).get("side_b", "")}
            return totals_payload(totals, when_iso=when,
                                  line=line, direction_counts=dc,
                                  side_names=sides)
        # sin dirección (aparición o sin línea): solo totales + datetime real
        return totals_payload(totals, when_iso=when)

    def flush(self) -> bool:
        """Envía un POST por evento pendiente, cada uno con su datetime real.

        Así, tras un offline, en el servidor quedan los datetime de
        creación uno por uno en vez de un agregado con la hora del envío.
        Solo marca synced lo que el servidor aceptó (201).
        """
        try:
            events = self.store.pending_events()
        except AttributeError:
            events = []
        if not events:
            self.on_status(True, "al dia")
            return True
        if self._online is False:
            # sin red (lo sabe el watcher): no se intenta, no hay error
            self.on_status(False, "sin conexión — envío pausado")
            return False
        sent, failed = 0, 0
        for ev in events:
            payload = self._event_payload(ev)
            if len(payload) <= 1:  # sin conteos válidos
                self.store.mark_synced([ev["id"]])
                continue
            dbg.log(f"API POST /api/trafico/ {payload}")
            try:
                r = requests.post(self.api + "/api/trafico/", json=payload,
                                  headers=self._headers(), timeout=self.timeout)
                if r.status_code in (401, 403):
                    dbg.log(f"API POST {r.status_code}: token inválido, re-registrando")
                    try:
                        from konta2r import fingerprint as fp_mod
                        self.register((self.cfg or {}).get("fingerprint", "")
                                      or fp_mod.fingerprint((self.cfg or {}).get("coords", "")),
                                      fp_mod.user_agent(),
                                      (self.cfg or {}).get("coords", ""))
                        r = requests.post(self.api + "/api/trafico/", json=payload,
                                          headers=self._headers(), timeout=self.timeout)
                    except Exception as exc2:  # noqa: BLE001
                        dbg.log(f"re-registro falló: {exc2}")
                        failed += 1
                        break
                    if r.status_code in (401, 403):
                        dbg.log("API sigue 401/403 tras re-registro; se reintenta luego")
                        failed += 1
                        break
                r.raise_for_status()
            except requests.RequestException as exc:
                if getattr(exc, "response", None) is None:
                    # sin respuesta HTTP = sin red: lo marca el watcher, sin timer
                    dbg.log(f"API sin red ({exc.__class__.__name__}): envío pausado")
                    if self._online is not False:
                        self._online = False
                        try:
                            if self.on_change:
                                self.on_change(False)
                        except Exception:  # noqa: BLE001
                            pass
                else:
                    dbg.log(f"API POST fallo: {exc.__class__.__name__}: {exc}")
                failed += 1
                break
            self.store.mark_synced([ev["id"]])
            sent += 1
        if failed:
            if self._online is False:
                self.on_status(False, "sin conexión — envío pausado")
                # sin timer: el watcher reanuda solo al reconectar
            else:
                self.on_status(False, f"pendientes: {failed} (enviados {sent})")
                self.schedule_retry()
            return False
        dbg.log(f"API sincronizados: {sent}")
        self.on_status(True, f"sincronizado ({sent})")
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
