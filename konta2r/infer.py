"""Inferencia onnxruntime. Entrada 'images', salida 'output0' [300,6]."""
from __future__ import annotations
import os
import numpy as np

from konta2r import settings as st

# COCO 80 clases
COCO = ['person', 'bicycle', 'car', 'motorcycle', 'airplane', 'bus', 'train', 'truck',
        'boat', 'traffic light', 'fire hydrant', 'stop sign', 'parking meter', 'bench',
        'bird', 'cat', 'dog', 'horse', 'sheep', 'cow', 'elephant', 'bear', 'zebra',
        'giraffe', 'backpack', 'umbrella', 'handbag', 'tie', 'suitcase', 'frisbee',
        'skis', 'snowboard', 'sports ball', 'kite', 'baseball bat', 'baseball glove',
        'skateboard', 'surfboard', 'tennis racket', 'bottle', 'wine glass', 'cup',
        'fork', 'knife', 'spoon', 'bowl', 'banana', 'apple', 'sandwich', 'orange',
        'broccoli', 'carrot', 'hot dog', 'pizza', 'donut', 'cake', 'chair', 'couch',
        'potted plant', 'bed', 'dining table', 'toilet', 'tv', 'laptop', 'mouse',
        'remote', 'keyboard', 'cell phone', 'microwave', 'oven', 'toaster', 'sink',
        'refrigerator', 'book', 'clock', 'vase', 'scissors', 'teddy bear',
        'hair drier', 'toothbrush']

# coco_id -> (counterKey, label, color, modelClass)
RULES = {
    0: ("person", "peaton", "#00ff00", "person"),
    1: ("bicycle", "bicicleta", "#0066ff", "bicycle"),
    2: ("car", "auto", "#ef4444", "car"),
    3: ("motorcycle", "moto", "#f97316", "motorcycle"),
    5: ("bus", "bus", "#8b5cf6", "bus"),
    7: ("truck", "camion", "#dc2626", "truck"),
    15: ("pet", "mascota", "#14b8a6", "cat"),
    16: ("pet", "mascota", "#10b981", "dog"),
    36: ("skater", "patineta", "#ff6600", "skateboard"),
}

COUNT_KEYS = st.CLASS_KEYS  # alias histórico; usar settings.CLASS_KEYS


def parse_output0(output: np.ndarray, conf: float = st.CONF_DEFAULT,
                  clases_activas: dict | None = None):
    """output: array plano o (300,6)/(1,300,6) con [x1,y1,x2,y2,score,classId].

    Retorna lista de dicts {bbox_model:[x1,y1,x2,y2], score, class_id,
    counterKey, label, color, modelClass}. Sin NMS (igual que web).
    """
    arr = np.asarray(output).reshape(-1, 6)
    dets = []
    for row in arr[:300]:
        x1, y1, x2, y2, score, cls = (float(row[0]), float(row[1]), float(row[2]),
                                      float(row[3]), float(row[4]), int(round(float(row[5]))))
        if score < conf:
            continue
        rule = RULES.get(cls)
        if not rule:
            continue
        key, label, color, model_class = rule
        if clases_activas is not None and not clases_activas.get(key, True):
            continue
        dets.append({"bbox_model": [x1, y1, x2, y2], "score": score,
                     "class_id": cls, "counterKey": key, "label": label,
                     "color": color, "modelClass": model_class})
    return dets


class Session:
    def __init__(self, model_path: str):
        import onnxruntime as ort
        if not os.path.exists(model_path):
            raise FileNotFoundError(model_path)
        opts = ort.SessionOptions()
        from konta2r import platform as pf
        opts.intra_op_num_threads = pf.infer_threads()
        self.sess = ort.InferenceSession(model_path, sess_options=opts,
                                         providers=["CPUExecutionProvider"])
        self.input_name = self.sess.get_inputs()[0].name

    def run(self, tensor: np.ndarray) -> np.ndarray:
        out = self.sess.run(["output0"], {self.input_name: tensor})
        return np.asarray(out[0])


def default_model_path(size: int = st.MODEL_DEFAULT) -> str:
    base = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models")
    alt = os.path.join(os.path.dirname(__file__), "..", "models")
    name = (f"yolo26n-{st.MODEL_SIZES[0]}.onnx" if int(size) == st.MODEL_SIZES[0]
            else f"yolo26n-{st.MODEL_SIZES[1]}.onnx")
    for cand in (os.path.join(base, name), os.path.join(alt, name), name):
        if os.path.exists(cand):
            return cand
    # ultimo recurso: junto al paquete
    here = os.path.join(os.path.dirname(__file__), "models", name)
    return here
