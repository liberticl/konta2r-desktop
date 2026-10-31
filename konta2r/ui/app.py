"""UI CustomTkinter: preview + overlay + contadores + botones + config."""
from __future__ import annotations
import datetime
import os
import threading
import time

try:
    import customtkinter as ctk
    from PIL import Image, ImageTk
    import cv2
    import numpy as np
except ImportError as _e:  # import diferido p/ tests sin GUI
    ctk, cv2, np, Image, ImageTk = None, None, None, None, None
    _IMPORT_ERR = _e
else:
    _IMPORT_ERR = None

from konta2r import config_store, fingerprint as fp_mod
from konta2r import preprocess as pre
from konta2r import infer as infer_mod
from konta2r import tracker as tracker_mod
from konta2r import store as store_mod
from konta2r import sync_client as sync_mod
from konta2r import export_csv as csv_mod
from konta2r.capture import Camera, enumerate_cameras

KEYS = ("person", "bicycle", "skater", "car", "motorcycle", "bus", "truck", "pet")
LABELS = {"person": "Peatones", "bicycle": "Bicis", "skater": "Patinetas",
          "car": "Autos", "motorcycle": "Motos", "bus": "Buses",
          "truck": "Camiones", "pet": "Mascotas"}


def require_gui():
    if _IMPORT_ERR is not None or ctk is None:
        raise RuntimeError(f"GUI no disponible: {_IMPORT_ERR}. "
                           "Instala requirements: pip install -r requirements.txt")


def hex_to_bgr(h: str):
    h = h.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (b, g, r)


class App:
    def __init__(self):
        require_gui()
        self.cfg = config_store.load()
        self.db = store_mod.Store()
        self.tracker = tracker_mod.Tracker()
        self.counts = {k: 0 for k in KEYS}
        self.dir_counts = {k: {"A->B": 0, "B->A": 0, "": 0} for k in KEYS}
        self.session_id = ("sesion_" + datetime.datetime.now().isoformat()
                           .replace(":", "-").replace(".", "-"))
        self.cam = Camera(self.cfg.get("camera_index", 0),
                          self.cfg.get("width", 1280), self.cfg.get("height", 720))
        self.sess = None
        self.model_size = int(self.cfg.get("model_size", 320))
        self.running, self.line_mode = False, False
        self.line_pts: list = []       # clicks display (x,y)
        self.frame, self.disp_boxes = None, []
        self.recording, self.writer = False, None
        self._build_ui()
        self._load_model_async()

    # ---- UI ----
    def _build_ui(self):
        ctk.set_appearance_mode("dark")
        self.root = ctk.CTk()
        self.root.title("konta2r-desktop")
        self.root.geometry("1100x700")
        self.lbl_status = ctk.CTkLabel(self.root, text="iniciando...")
        self.lbl_status.pack(pady=2)
        body = ctk.CTkFrame(self.root)
        body.pack(fill="both", expand=True, padx=8, pady=4)
        self.canvas = ctk.CTkCanvas(body, width=760, height=520,
                                    bg="black", highlightthickness=0)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind("<Button-1>", self._on_canvas_click)
        side = ctk.CTkFrame(body, width=300)
        side.pack(side="right", fill="y", padx=6)
        self.count_labels = {}
        for k in KEYS:
            row = ctk.CTkFrame(side)
            row.pack(fill="x", pady=1)
            ctk.CTkLabel(row, text=LABELS[k], width=110).pack(side="left")
            lbl = ctk.CTkLabel(row, text="0", width=60)
            lbl.pack(side="left")
            self.count_labels[k] = lbl
        for txt, cmd in [("Grabar", self.toggle_record),
                         ("Foto", self.save_photo),
                         ("CSV", self.save_csv),
                         ("Linea", self.toggle_line),
                         ("Config", self.open_config)]:
            ctk.CTkButton(side, text=txt, command=cmd).pack(fill="x", pady=2)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    # ---- modelo ----
    def _load_model_async(self):
        def _t():
            try:
                path = infer_mod.default_model_path(self.model_size)
                if not os.path.exists(path):
                    self._status(f"modelo no encontrado: {path}")
                    return
                self.sess = infer_mod.Session(path)
                self._status(f"modelo {self.model_size}px listo")
                self.start()
            except Exception as exc:  # noqa: BLE001
                self._status(f"error modelo: {exc}")
        threading.Thread(target=_t, daemon=True).start()

    def _status(self, msg):
        try:
            self.lbl_status.configure(text=msg)
        except Exception:
            pass

    # ---- loop ----
    def start(self):
        if not self.cam.open():
            cams = enumerate_cameras()
            self._status(f"sin camara idx {self.cam.index}. Disponibles: {cams}")
            return
        self.running = True
        threading.Thread(target=self._loop, daemon=True).start()
        self._render_schedule()

    def _loop(self):
        conf = float(self.cfg.get("conf_threshold", 0.50))
        while self.running:
            ok, frame = self.cam.read()
            if not ok or frame is None:
                time.sleep(0.05)
                continue
            self.frame = frame
            if self.sess is None:
                time.sleep(0.05)
                continue
            try:
                tensor, meta = pre.preprocess(frame, self.model_size)
                raw = self.sess.run(tensor)
            except Exception:  # noqa: BLE001
                time.sleep(0.05)
                continue
            dets = infer_mod.parse_output0(raw, conf, self.cfg.get("clases_activas"))
            h, w = frame.shape[:2]
            disp_w, disp_h = 760, 520
            boxes, now = [], int(time.time() * 1000)
            for d in dets:
                src = pre.model_box_to_src(d["bbox_model"], meta)
                x, y, bw, bh = pre.src_to_display(src, w, h, disp_w, disp_h)
                boxes.append({"bbox": [x, y, bw, bh], "counterKey": d["counterKey"],
                              "label": d["label"], "color": d["color"],
                              "score": d["score"], "modelClass": d["modelClass"]})
            line = self._active_line(disp_w, disp_h)
            for ev in self.tracker.update(boxes, now, line):
                self._register(ev["track"], ev["direction"])
            self.disp_boxes = boxes
            if self.recording and self.writer is not None:
                try:
                    self.writer.write(self._overlay(frame.copy()))
                except Exception:  # noqa: BLE001
                    pass

    def _active_line(self, dw, dh):
        ln = self.cfg.get("line")
        if ln:
            return {"start": {"x": ln["x1"] * dw, "y": ln["y1"] * dh},
                    "end": {"x": ln["x2"] * dw, "y": ln["y2"] * dh}}
        if len(self.line_pts) == 2:
            (x1, y1), (x2, y2) = self.line_pts
            return {"start": {"x": x1, "y": y1}, "end": {"x": x2, "y": y2}}
        return None

    def _register(self, track, direction):
        key = track["counterKey"]
        self.counts[key] = self.counts.get(key, 0) + 1
        self.dir_counts.setdefault(key, {}).setdefault(direction, 0)
        self.dir_counts[key][direction] += 1
        now = datetime.datetime.now()
        lat, lon = "", ""
        if self.cfg.get("coords"):
            parts = self.cfg["coords"].split(",")
            if len(parts) == 2:
                lat, lon = parts[0].strip(), parts[1].strip()
        try:
            self.db.save_event(
                session_id=self.session_id, timestamp_iso=now.isoformat(),
                date=now.strftime("%d-%m-%Y"), time=now.strftime("%H:%M:%S"),
                detected=track.get("label", ""), detected_key=key,
                model_class=track.get("modelClass", ""), direction=direction or "",
                lat=lat, lon=lon, acc="")
        except Exception:  # noqa: BLE001
            pass
        try:
            self.count_labels[key].configure(text=str(self.counts[key]))
        except Exception:  # noqa: BLE001
            pass

    # ---- render ----
    def _render_schedule(self):
        try:
            self._render()
        finally:
            if self.running:
                self.root.after(66, self._render_schedule)

    def _render(self):
        self.canvas.delete("all")
        if self.frame is None:
            return
        disp_w, disp_h = 760, 520
        small = cv2.resize(self.frame, (disp_w, disp_h))
        img = Image.fromarray(cv2.cvtColor(small, cv2.COLOR_BGR2RGB))
        self._tk = ImageTk.PhotoImage(img)
        self.canvas.create_image(0, 0, anchor="nw", image=self._tk)
        for b in self.disp_boxes:
            x, y, w, h = b["bbox"]
            self.canvas.create_rectangle(x, y, x + w, y + h,
                                         outline=b["color"], width=2)
            self.canvas.create_text(x, max(0, y - 8), anchor="nw",
                                    text=f"{b['label']} {int(b['score']*100)}%",
                                    fill=b["color"])
        line = self._active_line(disp_w, disp_h)
        if line:
            self.canvas.create_line(line["start"]["x"], line["start"]["y"],
                                    line["end"]["x"], line["end"]["y"],
                                    fill="red", width=3, dash=(8, 6))
            self.canvas.create_text(line["start"]["x"] + 6, line["start"]["y"] - 16,
                                    text="A", fill="red")
            self.canvas.create_text(line["end"]["x"] + 6, line["end"]["y"] - 16,
                                    text="B", fill="red")

    def _overlay(self, frame):
        h, w = frame.shape[:2]
        for b in self.disp_boxes:
            continue  # grabacion guarda frame crudo (simple)
        return frame

    # ---- acciones ----
    def _on_canvas_click(self, ev):
        if not self.line_mode:
            return
        self.line_pts.append((ev.x, ev.y))
        if len(self.line_pts) == 2:
            (x1, y1), (x2, y2) = self.line_pts
            self.cfg["line"] = {"x1": x1 / 760, "y1": y1 / 520,
                                "x2": x2 / 760, "y2": y2 / 520}
            config_store.save(self.cfg)
            self.line_mode = False
            self.line_pts = []

    def toggle_line(self):
        if self.cfg.get("line"):
            self.cfg["line"] = None
            config_store.save(self.cfg)
            self.line_pts = []
            self._status("linea borrada; clic Linea para crear otra")
        else:
            self.line_mode = not self.line_mode
            self.line_pts = []
            self._status("modo linea: haz 2 clics en el preview" if self.line_mode
                         else "modo linea off")

    def toggle_record(self):
        if not self.recording:
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            path = os.path.join(os.path.expanduser("~"),
                                f"grabacion_konta2r_{int(time.time())}.mp4")
            h, w = (self.frame.shape[:2] if self.frame is not None else (720, 1280))
            self.writer = cv2.VideoWriter(path, fourcc, 20.0, (w, h))
            self.recording = True
            self._status(f"grabando: {path}")
        else:
            self.recording = False
            try:
                self.writer.release()
            except Exception:  # noqa: BLE001
                pass
            self.writer = None
            self._status("grabacion detenida")

    def save_photo(self):
        if self.frame is None:
            return
        path = os.path.join(os.path.expanduser("~"),
                            f"foto_konta2r_{int(time.time())}.png")
        cv2.imwrite(path, self.frame)
        self._status(f"foto: {path}")

    def save_csv(self):
        path = os.path.join(os.path.expanduser("~"),
                            f"detecciones_{datetime.date.today()}.csv")
        csv_mod.export_events_to_csv(self.db.all_events(), path)
        self._status(f"CSV: {path}")

    def open_config(self):
        win = ctk.CTkToplevel(self.root)
        win.title("Configuracion")
        win.geometry("420x560")
        # sliders
        def row_slider(label, key, lo, hi, fmt="{}"):
            ctk.CTkLabel(win, text=label).pack()
            var = ctk.DoubleVar(value=float(self.cfg.get(key, lo)))
            lbl = ctk.CTkLabel(win, text=fmt.format(var.get()))
            lbl.pack()
            def _cb(v):
                self.cfg[key] = round(float(v), 2) if isinstance(self.cfg.get(key), float) else int(float(v))
                lbl.configure(text=fmt.format(self.cfg[key]))
            ctk.CTkSlider(win, from_=lo, to=hi, variable=var,
                          command=_cb).pack(fill="x", padx=12)
        row_slider("Camara index", "camera_index", 0, 8)
        row_slider("Confianza", "conf_threshold", 0.1, 0.9)
        row_slider("Sync minutos", "sync_interval_min", 1, 60)
        row_slider("Modelo (320/640)", "model_size", 320, 640)
        ctk.CTkLabel(win, text="Clases activas").pack(pady=(8, 0))
        self._cls_vars = {}
        for k in KEYS:
            v = ctk.BooleanVar(value=bool(self.cfg["clases_activas"].get(k, True)))
            self._cls_vars[k] = v
            ctk.CTkCheckBox(win, text=LABELS[k], variable=v).pack(anchor="w", padx=20)
        ctk.CTkLabel(win, text="Nombre dispositivo").pack()
        e_name = ctk.CTkEntry(win)
        e_name.insert(0, self.cfg.get("device_name", ""))
        e_name.pack(fill="x", padx=12)
        ctk.CTkLabel(win, text="Coords lat,lon").pack()
        e_coords = ctk.CTkEntry(win)
        e_coords.insert(0, self.cfg.get("coords", ""))
        e_coords.pack(fill="x", padx=12)

        def _save():
            for k, v in self._cls_vars.items():
                self.cfg["clases_activas"][k] = bool(v.get())
            ms = int(self.cfg.get("model_size", 320))
            self.cfg["model_size"] = 640 if ms >= 480 else 320
            self.cfg["device_name"] = e_name.get().strip()[:200]
            self.cfg["coords"] = e_coords.get().strip()
            config_store.save(self.cfg)
            win.destroy()
            self._status("config guardada (modelo aplica al reiniciar)")
        ctk.CTkButton(win, text="Guardar", command=_save).pack(pady=10)

    def close(self):
        self.running = False
        try:
            if self.recording and self.writer is not None:
                self.writer.release()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.cam.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.root.destroy()
        except Exception:  # noqa: BLE001
            pass

    def run(self):
        self.root.mainloop()


def main(argv=None):
    require_gui()
    app = App()
    # ensure fingerprint + register en background (no bloquea UI)
    cfg = app.cfg
    if not cfg.get("fingerprint"):
        cfg["fingerprint"] = fp_mod.fingerprint(cfg.get("coords", ""))
        config_store.save(cfg)

    def _bg():
        try:
            client = sync_mod.SyncClient(cfg.get("api_base", "https://andeschileong.cl"),
                                         app.db, cfg, on_status=lambda ok, m: None)
            if not cfg.get("token"):
                client.register(cfg["fingerprint"], fp_mod.user_agent(),
                                cfg.get("coords", ""))
                config_store.save(cfg)
            client.schedule_periodic(float(cfg.get("sync_interval_min", 5)))
            client.flush()
        except Exception:  # noqa: BLE001
            pass
    threading.Thread(target=_bg, daemon=True).start()
    app.run()
    return 0
