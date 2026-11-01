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
from konta2r import debug as dbg_mod
from konta2r import platform as pf_mod
from konta2r import settings as st_mod
from konta2r.capture import Camera, enumerate_cameras, list_cameras, camera_label, label_to_index

# Única definición en settings.py (aquí solo alias cortos).
KEYS = st_mod.CLASS_KEYS
LABELS = st_mod.CLASS_LABELS


def require_gui():
    if _IMPORT_ERR is not None or ctk is None:
        raise RuntimeError(f"GUI no disponible: {_IMPORT_ERR}. "
                           f"{pf_mod.tk_install_hint()}")
    if pf_mod.is_headless():
        raise RuntimeError("Sin pantalla (headless). Usa una sesión con "
                           "escritorio o X-forwarding, o el modo sin GUI.")


class App:
    def __init__(self):
        require_gui()
        self.cfg = config_store.load()
        if not os.path.exists(config_store.CONFIG_PATH):
            # primera ejecución: modelo según plataforma/RAM
            self.cfg["model_size"] = st_mod.default_model_size()
        self.db = store_mod.Store()
        self.tracker = tracker_mod.Tracker()
        self.counts = {k: 0 for k in KEYS}
        self.dir_counts = {k: {"A->B": 0, "B->A": 0, "": 0} for k in KEYS}
        self.session_id = (st_mod.SESSION_PREFIX + datetime.datetime.now().isoformat()
                           .replace(":", "-").replace(".", "-"))
        self.cam = Camera(self.cfg.get("camera_index", 0),
                          self.cfg.get("width", st_mod.CAMERA_WIDTH_DEFAULT), self.cfg.get("height", st_mod.CAMERA_HEIGHT_DEFAULT))
        self.sess = None
        self.model_size = int(self.cfg.get("model_size", st_mod.MODEL_DEFAULT))
        self.running, self.line_mode = False, False
        self.measuring = False
        self.sync_client = None
        self._session_line = None  # línea no persistente (solo memoria)
        self.debug_localhost = False  # solo sesión, no persistente, default off
        self.debug_port = st_mod.DEBUG_PORT_DEFAULT  # solo sesión; "" = sin puerto
        self.btn_measure = None
        self.lbl_measure = None
        self._term_win = None
        self._term_text = None
        self.line_pts: list = []       # clicks display (x,y)
        self.mouse_pos = None          # rubber-band preview (web parity)
        self.avail_cams: list = []
        self.cam_options: dict = {}
        self._status_pending_cam = None
        self.cam_var = None
        self.cam_menu = None
        self.disp_w, self.disp_h = st_mod.DISPLAY_W_DEFAULT, st_mod.DISPLAY_H_DEFAULT  # se ajusta al canvas real
        self.lbl_net = None
        self.frame, self.disp_boxes = None, []
        self.recording, self.writer = False, None
        self._rec_count = 0
        self._ui_thread = threading.get_ident()
        self._build_ui()
        self._load_model_async()

    # ---- UI ----
    def _build_ui(self):
        ctk.set_appearance_mode("dark")
        self.root = ctk.CTk()
        self.root.title("konta2r-desktop")
        self.root.geometry("1100x700")
        self.root.minsize(820, 520)
        body = ctk.CTkFrame(self.root)
        body.pack(fill="both", expand=True, padx=8, pady=8)
        self.canvas = ctk.CTkCanvas(body, bg="black", highlightthickness=0)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind("<Button-1>", self._on_canvas_click)
        self.canvas.bind("<Motion>", self._on_canvas_move)
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        side = ctk.CTkScrollableFrame(body, width=280)
        side.pack(side="right", fill="y", padx=(6, 0))
        self.lbl_measure = ctk.CTkLabel(side, text="● Sin medición", text_color="gray")
        self.lbl_measure.pack(anchor="w", pady=(0, 2))
        self.btn_measure = ctk.CTkButton(side, text="▶ Iniciar medición",
                                         fg_color="green", command=self.toggle_measure)
        self.btn_measure.pack(fill="x", pady=(0, 4))
        self.lbl_net = ctk.CTkLabel(side, text="● Red: …", text_color="gray")
        self.lbl_net.pack(anchor="w", pady=(0, 6))
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
                         ("Config", self.open_config),
                         ("Terminal", self.toggle_terminal)]:
            ctk.CTkButton(side, text=txt, command=cmd).pack(fill="x", pady=2)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    # ---- modelo ----
    def _load_model_async(self):
        def _t():
            try:
                path = infer_mod.default_model_path(self.model_size)
                if not os.path.exists(path):
                    self._status(f"modelo no encontrado: {path}")
                    self._toast(f"Modelo no encontrado: {path}")
                    return
                want = st_mod.MODEL_FILES.get(int(self.model_size), "")
                if want and os.path.basename(path) != want:
                    self._status(f"modelo {self.model_size}px ausente, usando {os.path.basename(path)}")
                self.sess = infer_mod.Session(path)
                self._status(f"modelo {self.model_size}px listo")
                self._toast(f"Modelo {self.model_size}px listo")
                self.start()
            except Exception as exc:  # noqa: BLE001
                self._status(f"error modelo: {exc}")
                self._toast(f"Error modelo: {exc}")
        threading.Thread(target=_t, daemon=True).start()

    def _ui_after(self, fn):
        """Ejecuta fn en el hilo de Tk (los timers/watcher corren en otros)."""
        try:
            if threading.get_ident() == self._ui_thread:
                fn()
            else:
                self.root.after(0, fn)
        except Exception:
            pass

    def _status(self, msg):
        # Sin barra superior: todo va al debug.log + terminal en vivo.
        try:
            dbg_mod.log(msg)
        except Exception:
            pass

        def _show():
            try:
                if getattr(self, "_term_text", None) is not None:
                    self._term_text.configure(state="normal")
                    self._term_text.insert("end", f"{msg}\n")
                    self._term_text.see("end")
                    self._term_text.configure(state="disabled")
            except Exception:
                pass
        self._ui_after(_show)

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
            self._toast("Sin cámara: recarga y elige otra")
            self.running = False
            return
        if getattr(self, "_status_pending_cam", None) is not None:
            self._status(f"cámara {self._status_pending_cam} desconectada, usando {self.cam.index}")
            self._status_pending_cam = None
        self.running = True
        threading.Thread(target=self._loop, daemon=True).start()
        self._render_schedule()

    def _loop(self):
        conf = float(self.cfg.get("conf_threshold", st_mod.CONF_DEFAULT))
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
            disp_w, disp_h = self.disp_w, self.disp_h
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
                    self._rec_count += 1
                    every = max(1, int(self.cfg.get("record_every_n", st_mod.RECORD_EVERY_N_DEFAULT)))
                    if self._rec_count % every == 0:
                        self.writer.write(self._overlay(frame.copy()))
                except Exception:  # noqa: BLE001
                    pass

    def _line_norm(self):
        """Línea efectiva: persistente (config) o solo sesión (memoria)."""
        if self.cfg.get("line_persistent", True):
            return self.cfg.get("line")
        return self._session_line

    def _set_line(self, line):
        if self.cfg.get("line_persistent", True):
            self.cfg["line"] = line
            config_store.save(self.cfg)
            self._session_line = None
        else:
            self._session_line = line
        self._push_line_to_client()

    def _push_line_to_client(self):
        try:
            if self.sync_client is not None:
                self.sync_client.session_line = self._session_line
        except Exception:  # noqa: BLE001
            pass

    def _active_line(self, dw, dh):
        ln = self._line_norm()
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
                side_a=(self.cfg.get("side_a") or "")[:st_mod.SIDE_NAME_MAX],
                side_b=(self.cfg.get("side_b") or "")[:st_mod.SIDE_NAME_MAX],
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
        disp_w, disp_h = self.disp_w, self.disp_h
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
            sx, sy = line["start"]["x"], line["start"]["y"]
            ex, ey = line["end"]["x"], line["end"]["y"]
            self.canvas.create_line(sx, sy, ex, ey, fill="red", width=3, dash=(8, 6))
            # vértices rojos + etiquetas A/B por LADO (mitad -1=A, +1=B), como v2
            for px, py in ((sx, sy), (ex, ey)):
                self.canvas.create_oval(px - 5, py - 5, px + 5, py + 5, fill="red", width=0)
            dx, dy = ex - sx, ey - sy
            import math as _math
            ln = _math.hypot(dx, dy)
            if ln >= 1:
                mx, my = (sx + ex) / 2, (sy + ey) / 2
                nx, ny = -dy / ln, dx / ln  # normal hacia B (+1)
                sides = {"a": (self.cfg.get("side_a") or "")[:20],
                         "b": (self.cfg.get("side_b") or "")[:20]}
                for s, tag in ((-1, "A"), (1, "B")):
                    px, py = mx + nx * 46 * s, my + ny * 46 * s
                    self.canvas.create_oval(px - 16, py - 16, px + 16, py + 16,
                                            fill="black", width=0)
                    self.canvas.create_text(px, py, text=tag, fill="white",
                                            font=("Arial", 16, "bold"))
                    nm = sides["a"] if s < 0 else sides["b"]
                    if nm:
                        self.canvas.create_text(px, py + 36, text=nm, fill="white",
                                                font=("Arial", 11))

    def _media_path(self, prefix: str, ext: str) -> str:
        d = pf_mod.media_dir()
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, f"{prefix}_{int(time.time())}.{ext}")

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
            self._set_line({"x1": x1 / self.disp_w, "y1": y1 / self.disp_h,
                            "x2": x2 / self.disp_w, "y2": y2 / self.disp_h})
            self.line_mode = False
            self.line_pts = []
            self._toast("Línea guardada" + (" (persistente)" if self.cfg.get("line_persistent", True) else " (solo esta sesión)"))

    def _on_canvas_move(self, ev):
        self.mouse_pos = (ev.x, ev.y)

    def _on_canvas_resize(self, ev):
        if ev.width > 200 and ev.height > 150:
            self.disp_w, self.disp_h = int(ev.width), int(ev.height)

    def _on_net_change(self, online: bool):
        # viene de la hebra watcher: todo UI vía after (hilo principal)
        def _apply():
            try:
                if online:
                    self.lbl_net.configure(text="● Red: online", text_color="green")
                else:
                    self.lbl_net.configure(text="● Red: offline", text_color="red")
            except Exception:
                pass
            self._toast("Red: reconectada, enviando" if online else "Red: sin conexión")
        try:
            self.root.after(0, _apply)
        except Exception:
            pass

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
        self.cam = Camera(idx, self.cfg.get("width", st_mod.CAMERA_WIDTH_DEFAULT), self.cfg.get("height", st_mod.CAMERA_HEIGHT_DEFAULT))
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
        if self._line_norm():
            self.cfg["line"] = None
            self._session_line = None
            if self.cfg.get("line_persistent", True):
                config_store.save(self.cfg)
            self._push_line_to_client()
            self.line_pts = []
            self._toast("Línea borrada")
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

    def _debug_url(self) -> str:
        port = (getattr(self, "debug_port", "") or "").strip()
        if port:
            if not port.isdigit() or not (1 <= int(port) <= 65535):
                return f"{st_mod.DEBUG_HOST}:{st_mod.DEBUG_PORT_DEFAULT}"
            return f"{st_mod.DEBUG_HOST}:{int(port)}"
        return st_mod.DEBUG_HOST

    def _effective_api(self) -> str:
        if getattr(self, "debug_localhost", False):
            return self._debug_url()
        return (self.cfg.get("api_base") or st_mod.API_BASE_DEFAULT).rstrip("/")

    def _ensure_sync_client(self):
        api = self._effective_api()
        if self.sync_client is None:
            self.sync_client = sync_mod.SyncClient(
                api, self.db, self.cfg,
                on_status=lambda ok, m: self._status(m))
        else:
            self.sync_client.api = api
        self.sync_client.session_line = self._session_line
        return self.sync_client

    def toggle_terminal(self):
        """Terminal de debug estilo web (log en vivo + archivo)."""
        if getattr(self, "_term_win", None) is not None:
            try:
                self._term_win.destroy()
            except Exception:  # noqa: BLE001
                pass
            self._term_win = None
            self._term_text = None
            return
        win = ctk.CTkToplevel(self.root)
        win.title(f"Debug — {dbg_mod.LOG_PATH}")
        win.geometry("560x340")
        self._term_win = win
        txt = ctk.CTkTextbox(win, wrap="word")
        txt.pack(fill="both", expand=True, padx=8, pady=8)
        try:
            for line in dbg_mod.read_tail(200):
                txt.insert("end", line + "\n")
            txt.see("end")
        except Exception:  # noqa: BLE001
            pass
        txt.configure(state="disabled")
        self._term_text = txt
        ctk.CTkLabel(win, text=f"Archivo: {dbg_mod.LOG_PATH}",
                     text_color="gray").pack(pady=(0, 6))
        win.protocol("WM_DELETE_WINDOW", self.toggle_terminal)

    def _start_measure(self):
        if self.sess is None:
            self._status("modelo aún cargando, espera…")
            return
        if not self.running:
            self.start()
            if not self.running:
                return
        # sesión nueva + contadores en cero
        self.session_id = (st_mod.SESSION_PREFIX + datetime.datetime.now().isoformat()
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
            cl.schedule_periodic(float(self.cfg.get("sync_interval_min", st_mod.SYNC_INTERVAL_DEFAULT)))
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
            fourcc = cv2.VideoWriter_fourcc(*st_mod.RECORD_FOURCC)
            path = self._media_path("grabacion_konta2r", "mp4")
            every = max(1, int(self.cfg.get("record_every_n", st_mod.RECORD_EVERY_N_DEFAULT)))
            fps = st_mod.RECORD_FPS / every  # duración 1:1 aunque se salten frames
            self._rec_count = 0
            h, w = (self.frame.shape[:2] if self.frame is not None
                    else (st_mod.CAMERA_HEIGHT_DEFAULT, st_mod.CAMERA_WIDTH_DEFAULT))
            self.writer = cv2.VideoWriter(path, fourcc, fps, (w, h))
            self.recording = True
            self._toast(f"Grabando 1 de cada {every} (~/konta2r)")
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
        path = self._media_path("foto_konta2r", "png")
        cv2.imwrite(path, self.frame)
        self._toast(f"Foto: {path}")

    def save_csv(self):
        path = os.path.join(pf_mod.media_dir(),
                            f"detecciones_{datetime.date.today()}.csv")
        os.makedirs(pf_mod.media_dir(), exist_ok=True)
        csv_mod.export_events_to_csv(self.db.all_events(), path)
        self._toast(f"CSV: {path}")

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
        row_slider("Confianza", "conf_threshold", st_mod.CONF_MIN, st_mod.CONF_MAX)
        row_slider("Sync minutos", "sync_interval_min", 1, 60)
        row_slider("Modelo (320/640)", "model_size", st_mod.MODEL_SIZES[0], st_mod.MODEL_SIZES[1])
        row_slider("Grabar 1 de cada N frames", "record_every_n", 1, st_mod.RECORD_EVERY_N_MAX)
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
        ctk.CTkLabel(scroll, text="Nombre lado A (referencia, máx 100)").pack()
        e_side_a = ctk.CTkEntry(scroll, placeholder_text="Ej: Norte / Entrada")
        e_side_a.insert(0, self.cfg.get("side_a", ""))
        e_side_a.pack(fill="x", padx=12)
        ctk.CTkLabel(scroll, text="Nombre lado B (referencia, máx 100)").pack()
        e_side_b = ctk.CTkEntry(scroll, placeholder_text="Ej: Sur / Salida")
        e_side_b.insert(0, self.cfg.get("side_b", ""))
        e_side_b.pack(fill="x", padx=12)
        ctk.CTkLabel(scroll, text="Línea de conteo").pack(pady=(8, 0))
        var_persist = ctk.BooleanVar(value=bool(self.cfg.get("line_persistent", True)))
        ctk.CTkCheckBox(scroll, text="Línea persistente entre sesiones",
                        variable=var_persist).pack(anchor="w", padx=20)
        ctk.CTkLabel(scroll, text="Apagado = la línea vive solo esta sesión",
                     text_color="gray").pack()
        # Debug: host a localhost, solo sesión, default off, con código 4 dígitos
        ctk.CTkLabel(scroll, text="Debug API").pack(pady=(10, 0))
        ctk.CTkLabel(scroll, text="Puerto localhost (vacío = sin puerto)").pack()
        e_dbg_port = ctk.CTkEntry(scroll, placeholder_text="8000")
        e_dbg_port.insert(0, getattr(self, "debug_port", "8000"))
        e_dbg_port.pack(fill="x", padx=12)
        lbl_dbg = ctk.CTkLabel(scroll, text="", wraplength=380, justify="left",
                               text_color="gray")
        lbl_dbg.pack(padx=12)

        def _refresh_dbg():
            if self.debug_localhost:
                lbl_dbg.configure(text=f"ON → {self._debug_url()} (solo esta sesión)")
                btn_dbg.configure(text="Desactivar debug", fg_color="orange")
            else:
                lbl_dbg.configure(text=f"OFF → {(self.cfg.get('api_base') or st_mod.API_BASE_DEFAULT)}")
                btn_dbg.configure(text="Activar debug → localhost", fg_color="gray")
        def _toggle_dbg():
            if self.debug_localhost:
                self.debug_localhost = False
                self._ensure_sync_client()
                self._status("debug OFF: API producción")
                _refresh_dbg()
                return
            code = f"{secrets.randbelow(9000) + 1000}"
            win2 = ctk.CTkToplevel(win)
            win2.title("Activar debug")
            win2.geometry("320x220")
            win2.attributes("-topmost", True)
            ctk.CTkLabel(win2, text="⚠ Apuntar API a localhost",
                         font=("Arial", 14, "bold")).pack(pady=(10, 2))
            ctk.CTkLabel(win2, text="Para activar, escribe este código:",
                         wraplength=280).pack()
            ctk.CTkLabel(win2, text=code,
                         font=("Courier", 26, "bold")).pack(pady=4)
            entry = ctk.CTkEntry(win2, placeholder_text="4 dígitos", justify="center")
            entry.pack(pady=4)
            err = ctk.CTkLabel(win2, text="", text_color="red")
            err.pack()
            entry.focus_set()
            def _ok(_ev=None):
                if entry.get().strip() == code:
                    self.debug_port = e_dbg_port.get().strip()
                    win2.destroy()
                    self.debug_localhost = True
                    self._ensure_sync_client()
                    self._status(f"debug ON: API {self._debug_url()} (no persistente)")
                    self._toast(f"Debug ON\n{self._debug_url()}")
                    _refresh_dbg()
                else:
                    err.configure(text="Código incorrecto")
            ctk.CTkButton(win2, text="Activar", fg_color="orange",
                          command=_ok).pack(pady=2)
            entry.bind("<Return>", _ok)
        btn_dbg = ctk.CTkButton(scroll, text="", command=_toggle_dbg)
        btn_dbg.pack(fill="x", padx=12, pady=4)
        btn_apply_port = ctk.CTkButton(scroll, text="Aplicar puerto",
                                       command=lambda: (
                                           setattr(self, "debug_port",
                                                   e_dbg_port.get().strip()),
                                           self._ensure_sync_client(),
                                           self._status(f"debug ON: API {self._debug_url()}"),
                                           _refresh_dbg()))
        _orig_refresh = _refresh_dbg
        def _refresh_dbg():
            _orig_refresh()
            try:
                if self.debug_localhost:
                    btn_apply_port.pack(fill="x", padx=12, pady=(0, 4))
                else:
                    btn_apply_port.pack_forget()
            except Exception:  # noqa: BLE001
                pass
        _refresh_dbg()

        def _save():
            for k, v in self._cls_vars.items():
                self.cfg["clases_activas"][k] = bool(v.get())
            ms = int(self.cfg.get("model_size", st_mod.MODEL_DEFAULT))
            new_size = st_mod.MODEL_SIZES[1] if ms >= st_mod.MODEL_SWITCH_THRESHOLD else st_mod.MODEL_SIZES[0]
            old_name = (self.cfg.get("device_name") or "")
            self.cfg["model_size"] = new_size
            self.cfg["record_every_n"] = min(max(1, int(self.cfg.get("record_every_n", st_mod.RECORD_EVERY_N_DEFAULT))), st_mod.RECORD_EVERY_N_MAX)
            self.cfg["device_name"] = e_name.get().strip()[:st_mod.DEVICE_NAME_MAX]
            self.cfg["coords"] = e_coords.get().strip()
            self.cfg["side_a"] = e_side_a.get().strip()[:st_mod.SIDE_NAME_MAX]
            self.cfg["side_b"] = e_side_b.get().strip()[:st_mod.SIDE_NAME_MAX]
            new_persist = bool(var_persist.get())
            old_persist = bool(self.cfg.get("line_persistent", True))
            self.cfg["line_persistent"] = new_persist
            if new_persist and not old_persist:
                # sesión -> archivo: la línea actual queda persistente
                if self._session_line and not self.cfg.get("line"):
                    self.cfg["line"] = self._session_line
                self._session_line = None
            elif not new_persist and old_persist:
                # archivo -> sesión: la línea actual vive solo hasta cerrar
                if self.cfg.get("line"):
                    self._session_line = self.cfg.get("line")
                    self.cfg["line"] = None
            config_store.save(self.cfg)
            self._push_line_to_client()
            win.destroy()
            # PATCH nombre en API si cambió y hay token (como la web)
            if self.cfg["device_name"] != old_name and self.cfg.get("token"):
                new_name = self.cfg["device_name"]
                def _rn():
                    try:
                        self._ensure_sync_client().rename(new_name)
                        self._status(f"nombre API: {new_name}")
                    except Exception as exc:  # noqa: BLE001
                        self._status(f"rename fallo: {exc}")
                threading.Thread(target=_rn, daemon=True).start()
            if self._reload_model(new_size):
                self._toast(f"Config guardada, recargando modelo {new_size}px")
            else:
                self._toast("Config guardada")
        ctk.CTkButton(win, text="Guardar", command=_save).pack(pady=10)

    def _reload_model(self, size: int):
        """Recarga .onnx en background sin reiniciar la app."""
        size = 640 if int(size) >= 480 else 320
        if self.sess is not None and int(self.model_size) == size:
            return False
        self.model_size = size
        self.sess = None
        self._status(f"cargando modelo {size}px…")

        def _t():
            try:
                path = infer_mod.default_model_path(size)
                if not os.path.exists(path):
                    self._status(f"modelo no encontrado: {path}")
                    self._toast(f"Modelo no encontrado: {path}")
                    return
                want = st_mod.MODEL_FILES.get(int(size), "")
                if want and os.path.basename(path) != want:
                    self._status(f"modelo {size}px ausente, usando {os.path.basename(path)}")
                    self._toast(f"Sin modelo {size}px, usando alternativo")
                sess = infer_mod.Session(path)
                self.sess = sess
                self._status(f"modelo {size}px listo")
                if not self.running:
                    self.start()
            except Exception as exc:  # noqa: BLE001
                self._status(f"error modelo: {exc}")
        threading.Thread(target=_t, daemon=True).start()
        return True

    def close(self):
        self.running = False
        try:
            if self.sync_client is not None:
                self.sync_client.stop_watcher()
                self.sync_client.cancel_retry()
        except Exception:  # noqa: BLE001
            pass
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
    try:
        dbg_mod.log(f"konta2r-desktop inicio ({st_mod.describe()})")
    except Exception:
        pass
    app = App()
    # ensure fingerprint + register en background (no bloquea UI)
    cfg = app.cfg
    if not cfg.get("fingerprint"):
        cfg["fingerprint"] = fp_mod.fingerprint(cfg.get("coords", ""))
        config_store.save(cfg)

    def _bg():
        # solo registro inicial; el envío periódico corre solo en medición
        try:
            client = sync_mod.SyncClient(cfg.get("api_base", st_mod.API_BASE_DEFAULT),
                                         app.db, cfg, on_status=lambda ok, m: None)
            app.sync_client = client
            try:
                client.start_watcher(interval=20.0,
                                     on_change=app._on_net_change)
                # estado inicial sin toast: solo el indicador
                _ok = client._probe()
                client._online = _ok
                def _init_lbl(ok=_ok):
                    try:
                        app.lbl_net.configure(
                            text="● Red: online" if ok else "● Red: offline",
                            text_color="green" if ok else "red")
                    except Exception:
                        pass
                app.root.after(0, _init_lbl)
            except Exception:  # noqa: BLE001
                pass
            if not cfg.get("token"):
                client.register(cfg["fingerprint"], fp_mod.user_agent(),
                                cfg.get("coords", ""))
                config_store.save(cfg)
        except Exception:  # noqa: BLE001
            pass
    threading.Thread(target=_bg, daemon=True).start()
    app.run()
    return 0
