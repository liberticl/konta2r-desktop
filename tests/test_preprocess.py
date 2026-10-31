import numpy as np
from konta2r import preprocess as P
from konta2r import infer as I


def test_preprocess_shape_and_range():
    frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    for s in (320, 640):
        t, meta = P.preprocess(frame, s)
        assert t.shape == (1, 3, s, s) and t.dtype == np.float32
        assert float(t.min()) >= 0.0 and float(t.max()) <= 1.0
        assert meta["src_w"] == 640 and meta["src_h"] == 480


def test_model_box_to_src_center():
    _, meta = P.preprocess(np.zeros((100, 200, 3), dtype=np.uint8), 320)
    s = meta["scale"]
    # centro del canvas deberia mapear al centro del frame
    box = [160 - 10, 160 - 10, 160 + 10, 160 + 10]
    x1, y1, x2, y2 = P.model_box_to_src(box, meta)
    assert abs((x1 + x2) / 2 - 100) < 2
    assert abs((y1 + y2) / 2 - 50) < 2


def test_parse_output0_conf_and_class_filter():
    out = np.zeros((300, 6), dtype=np.float32)
    out[0] = [10, 10, 50, 50, 0.9, 0]    # person ok
    out[1] = [10, 10, 50, 50, 0.2, 2]    # bajo conf
    out[2] = [10, 10, 50, 50, 0.9, 4]    # airplane: sin regla
    out[3] = [10, 10, 50, 50, 0.9, 16]   # dog->pet pero desactivado
    dets = I.parse_output0(out, 0.5, {"person": True, "pet": False,
                                      "car": True, "bicycle": True, "skater": True,
                                      "motorcycle": True, "bus": True, "truck": True})
    assert len(dets) == 1 and dets[0]["counterKey"] == "person"
