"""SQLite local: events con direccion + agregados pendientes de sync."""
from __future__ import annotations
import os
import sqlite3

from konta2r import platform as pf

APP_DIR = pf.config_dir()
DB_PATH = os.path.join(APP_DIR, "queue.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS events(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT, timestamp_iso TEXT, date TEXT, time TEXT,
  detected TEXT, detected_key TEXT, model_class TEXT, direction TEXT,
  side_a TEXT DEFAULT '', side_b TEXT DEFAULT '',
  lat TEXT, lon TEXT, acc TEXT, synced INTEGER DEFAULT 0
);
"""

KEY_TO_COL = {"car": "car", "person": "person", "bicycle": "bicycle",
              "motorcycle": "motorcycle", "truck": "truck", "bus": "bus",
              "skater": "skater", "pet": "pet"}


class Store:
    def __init__(self, path: str = DB_PATH):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.path = path
        self._init()

    def _conn(self):
        return sqlite3.connect(self.path)

    def _init(self):
        with self._conn() as c:
            c.executescript(SCHEMA)
            # migración liviana por si la tabla ya existía sin sides
            cols = {r[1] for r in c.execute("PRAGMA table_info(events)")}
            if "side_a" not in cols:
                c.execute("ALTER TABLE events ADD COLUMN side_a TEXT DEFAULT ''")
            if "side_b" not in cols:
                c.execute("ALTER TABLE events ADD COLUMN side_b TEXT DEFAULT ''")

    def save_event(self, session_id="", timestamp_iso="", date="", time="",
                   detected="", detected_key="", model_class="", direction="",
                   side_a="", side_b="",
                   lat="", lon="", acc="") -> int:
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO events(session_id,timestamp_iso,date,time,detected,"
                "detected_key,model_class,direction,side_a,side_b,lat,lon,acc) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (session_id, timestamp_iso, date, time, detected, detected_key,
                 model_class, direction, side_a, side_b, lat, lon, acc))
            return cur.lastrowid

    def all_events(self, limit: int = 100000):
        with self._conn() as c:
            c.row_factory = sqlite3.Row
            return [dict(r) for r in
                    c.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,))]

    def pending_totals(self) -> dict:
        """Agregados sin sincronizar (solo totales, sin direccion — API actual)."""
        totals = {k: 0 for k in KEY_TO_COL}
        with self._conn() as c:
            for (k,) in c.execute(
                    "SELECT detected_key FROM events WHERE synced=0"):
                if k in totals:
                    totals[k] += 1
        return totals

    def pending_ids(self):
        with self._conn() as c:
            return [r[0] for r in c.execute("SELECT id FROM events WHERE synced=0")]

    def pending_events(self, limit: int = 100000):
        """Eventos sin sincronizar para armar direction_counts."""
        with self._conn() as c:
            c.row_factory = sqlite3.Row
            return [dict(r) for r in c.execute(
                "SELECT * FROM events WHERE synced=0 ORDER BY id ASC LIMIT ?",
                (limit,))]

    def mark_synced(self, ids) -> int:
        ids = list(ids)
        if not ids:
            return 0
        q = ",".join("?" for _ in ids)
        with self._conn() as c:
            cur = c.execute(f"UPDATE events SET synced=1 WHERE id IN ({q})", ids)
            return cur.rowcount

    def pending_count(self) -> int:
        with self._conn() as c:
            return c.execute("SELECT COUNT(*) FROM events WHERE synced=0").fetchone()[0]
