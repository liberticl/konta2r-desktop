"""Tracker IoU+distancia con linea A/B. Port de contador.html."""
from __future__ import annotations
import math

TRACK_MAX_AGE = 1500      # ms
MIN_STABLE = 3            # frames
COOLDOWN = 1200           # ms
DEADZONE = 12             # px (signedDistance)


def foot_point(bbox):
    x, y, w, h = bbox  # x,y,w,h display
    return {"x": x + w / 2.0, "y": y + h}


def center_point(bbox):
    x, y, w, h = bbox
    return {"x": x + w / 2.0, "y": y + h / 2.0}


def dist(a, b):
    return math.hypot(a["x"] - b["x"], a["y"] - b["y"])


def iou(a, b):
    ax1, ay1, ax2, ay2 = a[0], a[1], a[0] + a[2], a[1] + a[3]
    bx1, by1, bx2, by2 = b[0], b[1], b[0] + b[2], b[1] + b[3]
    ix1, iy1, ix2, iy2 = max(ax1, bx1), max(ay1, by1), min(ax2, bx2), min(ay2, by2)
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    if not inter:
        return 0.0
    return inter / (a[2] * a[3] + b[2] * b[3] - inter)


def signed_distance(pt, line):
    return ((line["end"]["x"] - line["start"]["x"]) * (pt["y"] - line["start"]["y"])
            - (line["end"]["y"] - line["start"]["y"]) * (pt["x"] - line["start"]["x"]))


def get_side(pt, line):
    sd = signed_distance(pt, line)
    if abs(sd) <= DEADZONE:
        return 0
    return 1 if sd > 0 else -1


def direction_label(prev, cur):
    if prev == -1 and cur == 1:
        return "A->B"
    if prev == 1 and cur == -1:
        return "B->A"
    return ""


class Tracker:
    def __init__(self):
        self.tracks = {}
        self._next = 1

    def reset(self):
        self.tracks.clear()
        self._next = 1

    def _cleanup(self, now):
        for tid in [t for t, tr in self.tracks.items()
                    if now - tr["lastSeen"] > TRACK_MAX_AGE]:
            del self.tracks[tid]

    def _best_match(self, det, now, matched):
        best, best_score = None, float("inf")
        for tid, tr in self.tracks.items():
            if tid in matched or tr["counterKey"] != det["counterKey"]:
                continue
            if now - tr["lastSeen"] > TRACK_MAX_AGE:
                continue
            d = dist(tr["center"], det["center"])
            diag = math.hypot(det["bbox"][2], det["bbox"][3])
            max_d = max(60, min(180, diag * 0.8))
            ov = iou(tr["bbox"], det["bbox"])
            if d > max_d and ov < 0.05:
                continue
            score = d - ov * 80
            if score < best_score:
                best, best_score = tid, score
        return best

    def update(self, detections, now_ms: int, line=None):
        """detections: [{bbox[x,y,w,h], counterKey, label, color, score}].
        Retorna lista de eventos [{track, direction}]."""
        self._cleanup(now_ms)
        matched, events = set(), []
        for det in detections:
            det.setdefault("center", center_point(det["bbox"]))
            det.setdefault("foot", foot_point(det["bbox"]))
            tid = self._best_match(det, now_ms, matched)
            if tid is None:
                nid = self._next
                self._next += 1
                side = get_side(det["foot"], line) if line else None
                self.tracks[nid] = {
                    "id": nid, "counterKey": det["counterKey"], "label": det["label"],
                    "color": det["color"], "modelClass": det.get("modelClass", ""),
                    "bbox": det["bbox"], "center": det["center"], "foot": det["foot"],
                    "score": det["score"], "firstSeen": now_ms, "lastSeen": now_ms,
                    "stable": 1, "side": side, "lastCountAt": 0,
                    "movement": 0.0, "appearanceCounted": False,
                }
                continue
            tr = self.tracks[tid]
            prev_foot, prev_side = tr["foot"], tr["side"]
            tr.update({"bbox": det["bbox"], "center": det["center"],
                       "foot": det["foot"], "score": det["score"],
                       "color": det["color"], "lastSeen": now_ms,
                       "stable": tr["stable"] + 1})
            tr["movement"] += 0.0 if prev_foot is None else dist(prev_foot, det["foot"])
            if line:
                cur = get_side(det["foot"], line)
                if (prev_side not in (None, 0) and cur != 0 and prev_side != cur
                        and now_ms - tr["lastCountAt"] > COOLDOWN
                        and tr["movement"] > 8):
                    direction = direction_label(prev_side, cur)
                    tr["lastCountAt"] = now_ms
                    tr["movement"] = 0.0
                    events.append({"track": dict(tr), "direction": direction})
                if cur != 0:
                    tr["side"] = cur
            elif not tr["appearanceCounted"] and tr["stable"] >= MIN_STABLE:
                tr["appearanceCounted"] = True
                events.append({"track": dict(tr), "direction": ""})
            matched.add(tid)
        return events
