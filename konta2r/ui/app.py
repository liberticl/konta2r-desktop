"""UI CustomTkinter: preview + overlay + contadores + botones + config."""
from __future__ import annotations
import datetime
import os
import secrets
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
from konta2r import geocode as geocode_mod
from konta2r.capture import Camera, enumerate_cameras, list_cameras, camera_label, label_to_index

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
        self.measuring = False
        self.sync_client = None
        self.btn_measure = None
        self.lbl_measure = None
        self.line_pts: list = []       # clicks display (x,y)
        self.mouse_pos = None          # rubber-band preview (web parity)
        self.avail_cams: list = []
        self.cam_options: dict = {}
        self._status_pending_cam = None
        self.cam_var = None
        self.cam_menu = None
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
        top = ctk.CTkFrame(self.root)
        top.pack(fill="x", padx=8)
        self.lbl_measure = ctk.CTkLabel(top, text="● Sin medición", text_color="gray")
        self.lbl_measure.pack(side="left", padx=4)
        self.btn_measure = ctk.CTkButton(top, text="▶ Iniciar medición",
                                          fg_color="green", command=self.toggle_measure)
        self.btn_measure.pack(side="right", padx=4, pady=4)
        body = ctk.CTkFrame(self.root)
        body.pack(fill="both", expand=True, padx=8, pady=4)
        self.canvas = ctk.CTkCanvas(body, width=760, height=520,
                                    bg="black", highlightthickness=0)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind("<Button-1>", self._on_canvas_click)
        self.canvas.bind("<Motion>", self._on_canvas_move)
        side = ctk.CTkFrame(body, width=300)
        side.pack(side="right", fill="y", padx=6)
        # selector de cámara con nombre, solo disponibles
        ctk.CTkLabel(side, text="Cámara").pack(anchor="w")
        self.cam_options: dict[str, int] = {}
        self.cam_var = ctk.StringVar(value="")
        try:
            cams = list_cameras()
        except Exception:  # noqa: BLE001
            cams = []
        self.avail_cams = [i for i, _ in cams]
        for i, nm in cams:
            self.cam_options[camera_label(i, nm)] = i
        cur_idx = int(self.cfg.get("camera_index", 0))
        cur_label = next((lb for lb, ix in self.cam_options.items() if ix == cur_idx), None)
        if cur_label is None:
            # configurada no disponible (desconectada): solo disponibles
            cur_label = next(iter(self.cam_options), "0")
            self._status_pending_cam = cur_idx
        else:
            self._status_pending_cam = None
        self.cam_var.set(cur_label)
        self.cam_menu = ctk.CTkOptionMenu(
            side, variable=self.cam_var,
            values=list(self.cam_options) or ["0 · sin cámaras"],
            command=self._switch_camera)
        self.cam_menu.pack(fill="x", pady=(0, 4))
        ctk.CTkButton(side, text="↻ Recargar cámaras",
                      command=self._refresh_cameras).pack(fill="x", pady=(0, 6))
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

    def _toast(self, msg, ms: int = 2500):
        """Notificación push in-app: popup que se autocierra."""
        try:
            t = ctk.CTkToplevel(self.root)
            t.overrideredirect(True)
            t.attributes("-topmost", True)
            lbl = ctk.CTkLabel(t, text=msg, wraplength=300, justify="left")
            lbl.pack(padx=14, pady=10)
            try:
                t.update_idletasks()
                x = self.root.winfo_x() + self.root.winfo_width() - t.winfo_reqwidth() - 20
                y = self.root.winfo_y() + self.root.winfo_height() - t.winfo_reqheight() - 20
                t.geometry(f"+{max(0, x)}+{max(0, y)}")
            except Exception:  # noqa: BLE001
                pass
            t.after(ms, t.destroy)
        except Exception:  # noqa: BLE001
            pass

    # ---- loop ----
    def start(self):
        if not self.cam.open():
            try:
                cams = list_cameras()
            except Exception:  # noqa: BLE001
                cams = []
            names = ", ".join(camera_label(i, n) for i, n in cams) or "ninguna"
            self._status(f"cámara {self.cam.index} no disponible ({names}). Recarga y elige otra.")
            self.running = False
            return
        if getattr(self, "_status_pending_cam", None) is not None:
            self._status(f"cámara {self._status_pending_cam} desconectada, usando {self.cam.index}")
            self._status_pending_cam = None
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
            if self.measuring:
                for ev in self.tracker.update(boxes, now, line):
                    self._register(ev["track"], ev["direction"])
            else:
                # preview sin conteo: limpia tracks para no arrastrar
                if self.tracker.tracks:
                    self.tracker.reset()
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
        # (2) línea estilo web: roja punteada + etiquetas A/B + modo tinta + preview
        if self.line_mode:
            # tinta roja como en contador.html (rgba 255,0,0,0.18)
            self.canvas.create_rectangle(0, 0, disp_w, disp_h,
                                         fill="#ff0000", stipple="gray25", width=0)
            if len(self.line_pts) == 0:
                txt = "Modo línea - clic para inicio"
            else:
                txt = "Defina el segundo punto"
            self.canvas.create_text(disp_w / 2, 30, text=txt, fill="white",
                                    font=("Arial", 16))
        if len(self.line_pts) == 1 and self.line_mode and self.mouse_pos:
            (x1, y1) = self.line_pts[0]
            self.canvas.create_line(x1, y1, self.mouse_pos[0], self.mouse_pos[1],
                                    fill="red", width=3, dash=(8, 6))
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

    def _on_canvas_move(self, ev):
        self.mouse_pos = (ev.x, ev.y)

    def _refresh_cameras(self):
        try:
            cams = list_cameras()
        except Exception as exc:  # noqa: BLE001
            self._status(f"error enumerando cámaras: {exc}")
            return
        self.cam_options = {camera_label(i, nm): i for i, nm in cams}
        self.avail_cams = [i for i, _ in cams]
        if not self.cam_options:
            self.cam_menu.configure(values=["sin cámaras"])
            self._status("sin cámaras detectadas (¿desconectada?)")
            self.running = False
            return
        self.cam_menu.configure(values=list(self.cam_options))
        cur = int(self.cfg.get("camera_index", 0))
        if cur not in self.avail_cams:
            self._status(f"cámara {cur} desconectada. Elige una disponible.")
            # selecciona la primera sin cambiar sola
            first = next(iter(self.cam_options))
            self.cam_var.set(first)
            return
        self._status(f"cámaras: {[f'{i}' for i in self.avail_cams]}")

    def _switch_camera(self, choice):
        idx = label_to_index(choice)
        if idx is None:
            return
        was_running = self.running
        self.running = False
        try:
            self.cam.close()
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.15)
        self.cam = Camera(idx, self.cfg.get("width", 1280), self.cfg.get("height", 720))
        self.cfg["camera_index"] = idx
        config_store.save(self.cfg)
        self.tracker.reset()
        if was_running:
            self.start()
        else:
            # si el modelo ya cargó, arranca; si no, start() lo hará al cargar
            if self.sess is not None:
                self.start()
        self._status(f"cámara {idx}")

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

    def toggle_measure(self):
        if not self.measuring:
            self._start_measure()
        else:
            self._ask_finish()

    def _ensure_sync_client(self):
        if self.sync_client is None:
            self.sync_client = sync_mod.SyncClient(
                self.cfg.get("api_base", "https://andeschileong.cl"),
                self.db, self.cfg, on_status=lambda ok, m: None)
        return self.sync_client

    def _start_measure(self):
        if self.sess is None:
            self._status("modelo aún cargando, espera…")
            return
        if not self.running:
            self.start()
            if not self.running:
                return
        # sesión nueva + contadores en cero
        self.session_id = ("sesion_" + datetime.datetime.now().isoformat()
                           .replace(":", "-").replace(".", "-"))
        self.tracker.reset()
        self.counts = {k: 0 for k in KEYS}
        for k, lbl in self.count_labels.items():
            try:
                lbl.configure(text="0")
            except Exception:  # noqa: BLE001
                pass
        self.measuring = True
        try:
            cl = self._ensure_sync_client()
            cl.schedule_periodic(float(self.cfg.get("sync_interval_min", 5)))
            cl.flush()
        except Exception:  # noqa: BLE001
            pass
        self.btn_measure.configure(text="■ Finalizar medición", fg_color="red")
        self.lbl_measure.configure(text="● Midiendo…", text_color="red")
        self._status("medición iniciada: conteo + envío API activos")
        self._toast("Medición iniciada\nConteo y envío API activos")

    def _ask_finish(self):
        code = f"{secrets.randbelow(9000) + 1000}"
        win = ctk.CTkToplevel(self.root)
        win.title("Finalizar medición")
        win.geometry("360x230")
        win.attributes("-topmost", True)
        ctk.CTkLabel(win, text="⚠ Finalizar medición",
                     font=("Arial", 15, "bold")).pack(pady=(12, 4))
        ctk.CTkLabel(win, text="Para confirmar, escribe este código:",
                     wraplength=320).pack()
        ctk.CTkLabel(win, text=code,
                     font=("Courier", 28, "bold")).pack(pady=4)
        entry = ctk.CTkEntry(win, placeholder_text="4 dígitos", justify="center")
        entry.pack(pady=4)
        err = ctk.CTkLabel(win, text="", text_color="red")
        err.pack()
        entry.focus_set()

        def _ok(_ev=None):
            if entry.get().strip() == code:
                win.destroy()
                self._finish_measure()
            else:
                err.configure(text="Código incorrecto, sigue midiendo")
        ctk.CTkButton(win, text="Confirmar cierre", fg_color="red",
                      command=_ok).pack(pady=4)
        ctk.CTkButton(win, text="Seguir midiendo",
                      command=win.destroy).pack()
        entry.bind("<Return>", _ok)

    def _finish_measure(self):
        self.measuring = False
        try:
            if self.sync_client is not None:
                self.sync_client.flush()
                self.sync_client.cancel_retry()
        except Exception:  # noqa: BLE001
            pass
        self.btn_measure.configure(text="▶ Iniciar medición", fg_color="green")
        self.lbl_measure.configure(text="● Sin medición", text_color="gray")
        total = sum(self.counts.values())
        self._status(f"medición finalizada: {total} eventos")
        self._toast(f"Medición finalizada\n{total} eventos enviados a cola")

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
        win.geometry("440x600")
        # (3) scroll para que todo quepa
        scroll = ctk.CTkScrollableFrame(win)
        scroll.pack(fill="both", expand=True, padx=8, pady=8)

        def row_slider(label, key, lo, hi, fmt="{}"):
            ctk.CTkLabel(scroll, text=label).pack()
            var = ctk.DoubleVar(value=float(self.cfg.get(key, lo)))
            lbl = ctk.CTkLabel(scroll, text=fmt.format(var.get()))
            lbl.pack()

            def _cb(v):
                self.cfg[key] = round(float(v), 2) if isinstance(self.cfg.get(key), float) else int(float(v))
                lbl.configure(text=fmt.format(self.cfg[key]))
            ctk.CTkSlider(scroll, from_=lo, to=hi, variable=var,
                          command=_cb).pack(fill="x", padx=12)
        # selector de cámara en config (nombres, solo disponibles)
        ctk.CTkLabel(scroll, text="Cámara").pack()
        try:
            cams_cfg = list_cameras()
        except Exception:  # noqa: BLE001
            cams_cfg = []
        opts_cfg = {camera_label(i, n): i for i, n in cams_cfg} or {"sin cámaras": -1}
        cur_cfg = next((lb for lb, ix in opts_cfg.items()
                        if ix == int(self.cfg.get("camera_index", 0))), next(iter(opts_cfg)))
        cam_var_cfg = ctk.StringVar(value=cur_cfg)

        def _cfg_cam(choice):
            if label_to_index(choice) is None or label_to_index(choice) < 0:
                return
            self._switch_camera(choice)
            try:
                self.cam_var.set(choice)
            except Exception:  # noqa: BLE001
                pass
        ctk.CTkOptionMenu(scroll, variable=cam_var_cfg,
                          values=list(opts_cfg),
                          command=_cfg_cam).pack(fill="x", padx=12)
        row_slider("Confianza", "conf_threshold", 0.1, 0.9)
        row_slider("Sync minutos", "sync_interval_min", 1, 60)
        row_slider("Modelo (320/640)", "model_size", 320, 640)
        ctk.CTkLabel(scroll, text="Clases activas").pack(pady=(8, 0))
        self._cls_vars = {}
        for k in KEYS:
            v = ctk.BooleanVar(value=bool(self.cfg["clases_activas"].get(k, True)))
            self._cls_vars[k] = v
            ctk.CTkCheckBox(scroll, text=LABELS[k], variable=v).pack(anchor="w", padx=20)
        ctk.CTkLabel(scroll, text="Nombre dispositivo").pack()
        e_name = ctk.CTkEntry(scroll)
        e_name.insert(0, self.cfg.get("device_name", ""))
        e_name.pack(fill="x", padx=12)
        # dirección -> coords vía Nominatim gratuita (con confirmación)
        ctk.CTkLabel(scroll, text="Dirección (para obtener coords)").pack()
        e_addr = ctk.CTkEntry(scroll, placeholder_text="Ej: Cangreja 125, Valparaíso")
        e_addr.pack(fill="x", padx=12)
        card = ctk.CTkFrame(scroll)
        card.pack(fill="x", padx=12, pady=6)
        lbl_geo_title = ctk.CTkLabel(card, text="Sin búsqueda aún",
                                     wraplength=360, justify="left",
                                     font=("Arial", 13, "bold"))
        lbl_geo_title.pack(anchor="w", padx=8, pady=(6, 0))
        lbl_geo_coords = ctk.CTkLabel(card, text="", wraplength=360, justify="left",
                                      font=("Courier", 12))
        lbl_geo_coords.pack(anchor="w", padx=8)
        lbl_geo_full = ctk.CTkLabel(card, text="", wraplength=360, justify="left",
                                    text_color="gray", font=("Arial", 11))
        lbl_geo_full.pack(anchor="w", padx=8, pady=(0, 6))
        btn_usar = ctk.CTkButton(card, text="Usar estas coordenadas", state="disabled")
        btn_usar.pack(fill="x", padx=8, pady=(0, 8))
        self._geo_pending = None

        def _confirm_geo():
            if not self._geo_pending:
                return
            lat, lon, _name = self._geo_pending
            self.cfg["coords"] = f"{lat},{lon}"
            config_store.save(self.cfg)
            try:
                e_coords.delete(0, "end")
                e_coords.insert(0, self.cfg["coords"])
            except Exception:  # noqa: BLE001
                pass
            self._status(f"coords: {lat},{lon}")
            self._toast(f"Coordenadas guardadas\n{lat},{lon}")
            btn_usar.configure(state="disabled")
        btn_usar.configure(command=_confirm_geo)

        def _buscar():
            lbl_geo_title.configure(text="Buscando…")
            lbl_geo_coords.configure(text="")
            lbl_geo_full.configure(text="")
            btn_usar.configure(state="disabled")
            self._geo_pending = None
            addr = e_addr.get().strip()
            if not addr:
                lbl_geo_title.configure(text="Escribe una dirección")
                return

            def _t():
                try:
                    lat, lon, name = geocode_mod.forward(addr)
                    parts = [p.strip() for p in name.split(",")]
                    short = ", ".join(parts[:2]) if len(parts) >= 2 else name[:80]
                    self._geo_pending = (lat, lon, name)
                    lbl_geo_title.configure(text=short[:90])
                    lbl_geo_coords.configure(text=f"{lat}, {lon}")
                    lbl_geo_full.configure(text=name[:220])
                    btn_usar.configure(state="normal")
                except Exception as exc:  # noqa: BLE001
                    lbl_geo_title.configure(text="Sin resultados")
                    lbl_geo_full.configure(text=str(exc)[:200])
            threading.Thread(target=_t, daemon=True).start()
        ctk.CTkButton(scroll, text="Buscar dirección → coords",
                      command=_buscar).pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(scroll, text="Coords lat,lon").pack()
        e_coords = ctk.CTkEntry(scroll)
        e_coords.insert(0, self.cfg.get("coords", ""))
        e_coords.pack(fill="x", padx=12)
        ctk.CTkLabel(scroll, text="Fuente: Nominatim OSM (1 req/seg, gratis)",
                     text_color="gray").pack()

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
        # solo registro inicial; el envío periódico corre solo en medición
        try:
            client = sync_mod.SyncClient(cfg.get("api_base", "https://andeschileong.cl"),
                                         app.db, cfg, on_status=lambda ok, m: None)
            app.sync_client = client
            if not cfg.get("token"):
                client.register(cfg["fingerprint"], fp_mod.user_agent(),
                                cfg.get("coords", ""))
                config_store.save(cfg)
        except Exception:  # noqa: BLE001
            pass
    threading.Thread(target=_bg, daemon=True).start()
    app.run()
    return 0
