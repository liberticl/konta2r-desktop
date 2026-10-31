"""Export CSV con direccion (compatible con contador web)."""
from __future__ import annotations
import csv

HEADER = ["ID sesion", "fecha", "hora", "deteccion", "clase modelo",
          "direccion", "lado A", "lado B",
          "latitud", "longitud", "precision_m", "timestamp_iso"]


def export_events_to_csv(events: list[dict], path: str) -> str:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(HEADER)
        for e in events:
            w.writerow([e.get("session_id", ""), e.get("date", ""),
                        e.get("time", ""), e.get("detected", ""),
                        e.get("model_class", ""), e.get("direction", ""),
                        e.get("side_a", ""), e.get("side_b", ""),
                        e.get("lat", ""), e.get("lon", ""),
                        e.get("acc", ""), e.get("timestamp_iso", "")])
    return path
