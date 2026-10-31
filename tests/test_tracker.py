import time
from konta2r import tracker as T


def det(x, y, w=40, h=80, key="person"):
    return {"bbox": [x, y, w, h], "counterKey": key, "label": key,
            "color": "#fff", "score": 0.9, "modelClass": key}


def test_appearance_without_line_counts_once_after_stable():
    tr = T.Tracker()
    evs = []
    for i in range(5):
        evs += tr.update([det(10, 10)], now_ms=i * 100, line=None)
    assert len(evs) == 1 and evs[0]["direction"] == ""


def test_line_crossing_direction():
    tr = T.Tracker()
    line = {"start": {"x": 0, "y": 100}, "end": {"x": 200, "y": 100}}
    # foot y = y+h ; empieza arriba (side -1) y cruza abajo (side +1) => A->B
    t = 10_000_000  # base realista: web compara contra lastCountAt=0 con Date.now()
    got = []
    for y in (0, 10, 20, 40, 60, 90):
        got += tr.update([det(50, y)], now_ms=t, line=line)
        t += 300
    assert any(e["direction"] == "A->B" for e in got)


def test_cooldown_blocks_immediate_recount():
    tr = T.Tracker()
    line = {"start": {"x": 0, "y": 100}, "end": {"x": 200, "y": 100}}
    t = 0
    got = []
    ys = [0, 10, 40, 90, 0, 90]  # cruza, vuelve y cruza rapido
    for y in ys:
        got += tr.update([det(50, y)], now_ms=t, line=line)
        t += 300
    assert len([e for e in got if e["direction"]]) <= 1


def test_deadzone_no_side():
    line = {"start": {"x": 0, "y": 100}, "end": {"x": 200, "y": 100}}
    # sd = dx*(y-100) = 200*(y-100); |sd|<=12 solo ~sobre la linea (igual que web)
    assert T.get_side({"x": 50, "y": 100}, line) == 0
    assert T.get_side({"x": 50, "y": 80}, line) == -1
    assert T.get_side({"x": 50, "y": 120}, line) == 1
