import os, re, shutil, hashlib, threading, json, webbrowser, tempfile, struct
from datetime import datetime
from pathlib import Path
from typing import Optional
from collections import defaultdict
import tkinter as tk
from tkinter import filedialog, messagebox, Toplevel
from tkinter import ttk

import imagehash
from PIL import Image, ImageTk, ImageFilter, ImageStat
from send2trash import send2trash

try:
    import piexif
    HAS_PIEXIF = True
except ImportError:
    HAS_PIEXIF = False

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

# ══════════════════════════════════════════════════════════
#  COSTANTI
# ══════════════════════════════════════════════════════════
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.webp'}
VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv', '.m4v', '.wmv', '.flv',
                    '.hevc', '.3gp', '.ts', '.mts', '.m2ts'}
EXIF_EXTENSIONS  = {'.jpg', '.jpeg', '.tiff', '.tif'}
EXIF_DATE_TAGS   = (36867, 36868, 306)
EXIF_FMT         = '%Y:%m:%d %H:%M:%S'
MESI_IT = {1:"01-Gennaio",2:"02-Febbraio",3:"03-Marzo",4:"04-Aprile",
           5:"05-Maggio",6:"06-Giugno",7:"07-Luglio",8:"08-Agosto",
           9:"09-Settembre",10:"10-Ottobre",11:"11-Novembre",12:"12-Dicembre"}

# ── Palette ───────────────────────────────────────────────
BG="#161616"; BG2="#1f1f1f"; BG3="#2a2a2a"; BORDER="#333333"
FG="#e0e0e0"; FG_DIM="#666666"; FG_MID="#999999"
ACCENT="#c8a96e"; GREEN="#6ec87e"; RED_C="#c86e6e"; BLUE="#6e9ec8"; PURPLE="#a06ec8"
MONO=("Courier",10); MONO_B=("Courier",10,"bold"); TITLE_F=("Courier",12,"bold")

# ── Pattern per estrarre data dal nome file ────────────────
_DATE_PATTERNS = [
    re.compile(r'(\d{4})[-_](\d{2})[-_](\d{2})[T_-](\d{2})[-_:](\d{2})[-_:](\d{2})'),
    re.compile(r'(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})'),
    re.compile(r'(\d{4})[-_](\d{2})[-_](\d{2})'),
    re.compile(r'(\d{4})(\d{2})(\d{2})'),
    re.compile(r'(\d{2})[-_](\d{2})[-_](\d{4})'),
]

# ══════════════════════════════════════════════════════════
#  UTILITY CONDIVISE
# ══════════════════════════════════════════════════════════
def normalize(path: str) -> str:
    return os.path.normpath(os.path.abspath(path))

def unique_dest(folder: str, filename: str) -> str:
    dst = os.path.join(folder, filename)
    if not os.path.exists(dst): return dst
    base, ext = os.path.splitext(filename); i = 1
    while True:
        c = os.path.join(folder, f"{base}_{i}{ext}")
        if not os.path.exists(c): return c
        i += 1

def collect_files(folder: str, extensions: set, skip_dirs: set = None) -> list:
    skip_dirs = {normalize(s) for s in (skip_dirs or [])}
    result = []
    for root_dir, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if normalize(os.path.join(root_dir,d)) not in skip_dirs]
        for f in sorted(files):
            if Path(f).suffix.lower() in extensions:
                result.append(normalize(os.path.join(root_dir, f)))
    return result

# ── Cache ──────────────────────────────────────────────────
_hash_cache: dict = {}
_res_cache:  dict = {}

def get_phash(path: str) -> Optional[imagehash.ImageHash]:
    if path not in _hash_cache:
        try: _hash_cache[path] = imagehash.phash(Image.open(path))
        except Exception: _hash_cache[path] = None
    return _hash_cache[path]

def get_resolution(path: str) -> Optional[int]:
    if path not in _res_cache:
        try:
            with Image.open(path) as img: _res_cache[path] = img.width * img.height
        except Exception: _res_cache[path] = None
    return _res_cache[path]

# ── EXIF ───────────────────────────────────────────────────
def get_exif_date(path: str) -> Optional[datetime]:
    try:
        with Image.open(path) as img:
            exif = img._getexif()
            if not exif: return None
            for tag in EXIF_DATE_TAGS:
                s = exif.get(tag)
                if s:
                    try: return datetime.strptime(s.strip(), EXIF_FMT)
                    except ValueError: continue
    except Exception: pass
    return None

def get_exif_all(path: str) -> dict:
    """Restituisce dizionario tag→valore da EXIF (solo JPG/TIFF)."""
    try:
        with Image.open(path) as img:
            raw = img._getexif()
            if raw: return dict(raw)
    except Exception: pass
    return {}

def get_gps(path: str) -> Optional[tuple]:
    """Restituisce (lat, lon) dai tag GPS EXIF, o None."""
    try:
        from PIL.ExifTags import TAGS, GPSTAGS
        with Image.open(path) as img:
            exif = img._getexif()
            if not exif: return None
            gps_info = None
            for tag_id, val in exif.items():
                if TAGS.get(tag_id) == "GPSInfo":
                    gps_info = {GPSTAGS.get(k, k): v for k, v in val.items()}
                    break
            if not gps_info: return None
            def dms(d):
                deg, mn, sec = d
                return float(deg) + float(mn)/60 + float(sec)/3600
            lat = dms(gps_info["GPSLatitude"])
            lon = dms(gps_info["GPSLongitude"])
            if gps_info.get("GPSLatitudeRef","N") == "S": lat = -lat
            if gps_info.get("GPSLongitudeRef","E") == "W": lon = -lon
            return (lat, lon)
    except Exception: return None

def get_camera(path: str) -> str:
    try:
        from PIL.ExifTags import TAGS
        with Image.open(path) as img:
            exif = img._getexif()
            if not exif: return "Sconosciuta"
            make  = next((v for k,v in exif.items() if TAGS.get(k)=="Make"),  "")
            model = next((v for k,v in exif.items() if TAGS.get(k)=="Model"), "")
            cam = f"{make} {model}".strip()
            return cam[:40] if cam else "Sconosciuta"
    except Exception: return "Sconosciuta"

def get_file_date(path: str) -> Optional[datetime]:
    if Path(path).suffix.lower() in EXIF_EXTENSIONS:
        dt = get_exif_date(path)
        if dt: return dt
    try: return datetime.fromtimestamp(os.path.getmtime(path))
    except OSError: return None

def date_from_filename(path: str) -> Optional[datetime]:
    name = Path(path).stem
    for pat in _DATE_PATTERNS:
        m = pat.search(name)
        if m:
            g = [int(x) for x in m.groups()]
            try:
                if len(g) >= 6:
                    yr,mo,dy,hh,mm,ss = g[:6]
                    if mo > 12: yr,mo,dy = dy,mo,yr
                    return datetime(yr,mo,dy,hh,mm,ss)
                else:
                    yr,mo,dy = g[:3]
                    if mo > 12: yr,mo,dy = dy,mo,yr
                    return datetime(yr,mo,dy)
            except Exception: continue
    return None

# ── Priorità originale ─────────────────────────────────────
_DUP_PAT = re.compile(r"\(\d+\)\.")
def preferred_original(p1: str, p2: str) -> str:
    def numbered(p): return bool(_DUP_PAT.search(os.path.splitext(os.path.basename(p))[0]))
    n1,n2 = numbered(p1),numbered(p2)
    if n1 and not n2: return p2
    if n2 and not n1: return p1
    r1,r2 = get_resolution(p1),get_resolution(p2)
    if r1 and r2:
        if r1>r2: return p1
        if r2>r1: return p2
    try:
        s1,s2 = os.path.getsize(p1),os.path.getsize(p2)
        if s1>s2: return p1
        if s2>s1: return p2
    except OSError: pass
    return p1

# ── Qualità immagine ───────────────────────────────────────
def blur_score(path: str) -> float:
    """Varianza del Laplacian — più bassa = più sfocata."""
    try:
        with Image.open(path) as img:
            gray = img.convert("L").filter(ImageFilter.Kernel(
                size=3, kernel=[-1,-1,-1,-1,8,-1,-1,-1,-1], scale=1))
            stat = ImageStat.Stat(gray)
            return stat.var[0]
    except Exception: return -1.0

def exposure_score(path: str) -> tuple:
    """Restituisce (mean_brightness, is_dark, is_bright) — soglie 30 e 225."""
    try:
        with Image.open(path) as img:
            stat = ImageStat.Stat(img.convert("L"))
            mean = stat.mean[0]
            return (mean, mean < 30, mean > 225)
    except Exception: return (-1, False, False)

# ══════════════════════════════════════════════════════════
#  WIDGET HELPERS
# ══════════════════════════════════════════════════════════
def styled_button(parent, text, command, color=BG3, fg=FG, **kw):
    return tk.Button(parent, text=text, command=command,
                     bg=color, fg=fg, activebackground=BORDER, activeforeground=FG,
                     relief=tk.FLAT, cursor="hand2", bd=0, font=MONO, **kw)

def log_widget(parent):
    frame = tk.Frame(parent, bg=BG2)
    txt = tk.Text(frame, bg=BG2, fg=FG_MID, font=("Courier",9), wrap="word", relief=tk.FLAT, bd=0)
    sb  = tk.Scrollbar(frame, command=txt.yview, bg=BG3, troughcolor=BG2)
    txt.configure(yscrollcommand=sb.set)
    sb.pack(side=tk.RIGHT, fill=tk.Y); txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    return frame, txt

def folder_row(parent, var: tk.StringVar, label_text: str, width=22):
    row = tk.Frame(parent, bg=BG)
    tk.Label(row, text=label_text, font=MONO, bg=BG, fg=FG_MID, width=width, anchor="w").pack(side=tk.LEFT)
    tk.Entry(row, textvariable=var, font=MONO, bg=BG3, fg=FG,
             insertbackground=FG, relief=tk.FLAT, bd=0).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0,6))
    styled_button(row, "📂", lambda: var.set(filedialog.askdirectory() or var.get()),
                  padx=6, pady=2).pack(side=tk.LEFT)
    return row

def file_row(parent, var: tk.StringVar, label_text: str, filetypes=None):
    row = tk.Frame(parent, bg=BG)
    tk.Label(row, text=label_text, font=MONO, bg=BG, fg=FG_MID, width=22, anchor="w").pack(side=tk.LEFT)
    tk.Entry(row, textvariable=var, font=MONO, bg=BG3, fg=FG,
             insertbackground=FG, relief=tk.FLAT, bd=0).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0,6))
    ft = filetypes or [("Immagini","*.jpg *.jpeg *.png *.bmp *.tiff *.webp")]
    styled_button(row, "📄", lambda: var.set(filedialog.askopenfilename(filetypes=ft) or var.get()),
                  padx=6, pady=2).pack(side=tk.LEFT)
    return row

def section_header(parent, title, subtitle=""):
    top = tk.Frame(parent, bg=BG2, pady=8)
    top.pack(fill=tk.X)
    tk.Label(top, text=title, font=TITLE_F, bg=BG2, fg=ACCENT).pack(side=tk.LEFT, padx=14)
    if subtitle:
        tk.Label(top, text=subtitle, font=("Courier",9), bg=BG2, fg=FG_DIM).pack(side=tk.LEFT, padx=6)
    return top

def canvas_bar(parent, title, value, max_val, color, width=300):
    """Singola barra orizzontale per mini-grafici."""
    f = tk.Frame(parent, bg=BG2)
    tk.Label(f, text=f"{title:<26}", font=("Courier",9), bg=BG2, fg=FG_MID,
             anchor="w", width=26).pack(side=tk.LEFT)
    cv = tk.Canvas(f, width=width, height=14, bg=BG3, highlightthickness=0)
    cv.pack(side=tk.LEFT, padx=4)
    frac = min(value/max_val, 1.0) if max_val else 0
    cv.create_rectangle(0,1,int(width*frac),13, fill=color, outline="")
    tk.Label(f, text=str(value), font=("Courier",9,"bold"), bg=BG2, fg=color, width=6).pack(side=tk.LEFT)
    return f


# ══════════════════════════════════════════════════════════
#  TAB 1 — VISUALIZZA & ORGANIZZA  (con zoom/pan, confronto, filtri)
# ══════════════════════════════════════════════════════════
class VisualizzaTab:
    def __init__(self, nb):
        self.frame = tk.Frame(nb, bg=BG)
        nb.add(self.frame, text="  📷 Visualizza  ")
        self.photo_files = []; self.all_files = []
        self.current_idx = -1; self.current_image = None
        self.folder_path = None; self.deleted_path = None
        # Zoom/Pan
        self._zoom = 1.0; self._pan_x = 0; self._pan_y = 0
        self._drag_start = None; self._orig_pil = None
        self._build(); self._bind_keys()

    # ── Build ─────────────────────────────────────────────
    def _build(self):
        top = tk.Frame(self.frame, bg=BG2, pady=6)
        top.pack(fill=tk.X)
        tk.Label(top, text="VISUALIZZA & ORGANIZZA", font=TITLE_F, bg=BG2, fg=ACCENT).pack(side=tk.LEFT, padx=14)
        self.folder_lbl = tk.Label(top, text="Nessuna cartella", font=("Courier",9), bg=BG2, fg=FG_DIM)
        self.folder_lbl.pack(side=tk.RIGHT, padx=6)
        styled_button(top, "📂 Cartella", self.browse, padx=10, pady=3).pack(side=tk.RIGHT, padx=14)
        styled_button(top, "⚖ Confronto", self._open_compare, color="#1a1a3a", fg=BLUE, padx=8, pady=3).pack(side=tk.RIGHT, padx=4)

        # Filtri
        flt = tk.Frame(self.frame, bg=BG3, pady=4)
        flt.pack(fill=tk.X, padx=14, pady=(4,0))
        tk.Label(flt, text="Filtri:", font=MONO, bg=BG3, fg=FG_MID).pack(side=tk.LEFT, padx=6)
        tk.Label(flt, text="Anno:", font=MONO, bg=BG3, fg=FG_DIM).pack(side=tk.LEFT, padx=(10,2))
        self.flt_year = tk.Entry(flt, width=6, font=MONO, bg=BG2, fg=FG, insertbackground=FG, relief=tk.FLAT)
        self.flt_year.pack(side=tk.LEFT)
        tk.Label(flt, text="Dim.min(KB):", font=MONO, bg=BG3, fg=FG_DIM).pack(side=tk.LEFT, padx=(10,2))
        self.flt_min  = tk.Entry(flt, width=7, font=MONO, bg=BG2, fg=FG, insertbackground=FG, relief=tk.FLAT)
        self.flt_min.pack(side=tk.LEFT)
        tk.Label(flt, text="max(KB):", font=MONO, bg=BG3, fg=FG_DIM).pack(side=tk.LEFT, padx=(8,2))
        self.flt_max  = tk.Entry(flt, width=7, font=MONO, bg=BG2, fg=FG, insertbackground=FG, relief=tk.FLAT)
        self.flt_max.pack(side=tk.LEFT)
        styled_button(flt, "Applica", self._apply_filters, color="#2a2a1a", fg=ACCENT, padx=8, pady=2).pack(side=tk.LEFT, padx=10)
        styled_button(flt, "Reset",   self._reset_filters, padx=8, pady=2).pack(side=tk.LEFT)

        # Canvas per zoom/pan
        img_outer = tk.Frame(self.frame, bg=BG)
        img_outer.pack(fill=tk.BOTH, expand=True, padx=14, pady=(6,0))
        self.canvas = tk.Canvas(img_outer, bg=BG2, highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<MouseWheel>",       self._on_scroll)
        self.canvas.bind("<Button-4>",         self._on_scroll)
        self.canvas.bind("<Button-5>",         self._on_scroll)
        self.canvas.bind("<ButtonPress-1>",    self._drag_start_fn)
        self.canvas.bind("<B1-Motion>",        self._drag_move)
        self.canvas.bind("<Double-Button-1>",  self._zoom_reset)

        zoom_hint = tk.Label(self.frame, text="scroll=zoom  |  drag=pan  |  doppio click=reset",
                             font=("Courier",8), bg=BG, fg=FG_DIM)
        zoom_hint.pack()

        self.fname_lbl = tk.Label(self.frame, text="", font=("Courier",9), bg=BG, fg=FG_DIM)
        self.fname_lbl.pack(pady=(2,0))
        pb_out = tk.Frame(self.frame, bg=BG, height=3); pb_out.pack(fill=tk.X, padx=14, pady=(3,0))
        pb_out.pack_propagate(False)
        pb_bg = tk.Frame(pb_out, bg=BG3, height=3); pb_bg.pack(fill=tk.BOTH, expand=True)
        self.pb = tk.Frame(pb_bg, bg=ACCENT, height=3); self.pb.place(relwidth=0, relheight=1)

        ctrl = tk.Frame(self.frame, bg=BG, pady=8); ctrl.pack()
        bst  = dict(font=MONO_B, relief=tk.FLAT, cursor="hand2", bd=0, padx=16, pady=6)
        self.prev_btn = tk.Button(ctrl, text="◀ Prec",      bg=BG3, fg=FG_MID, command=self.show_prev, state=tk.DISABLED, **bst)
        self.prev_btn.grid(row=0,column=0,padx=5)
        self.keep_btn = tk.Button(ctrl, text="✓ Tieni  [K]",bg="#1a3a1a",fg=GREEN,command=self.keep,state=tk.DISABLED, **bst)
        self.keep_btn.grid(row=0,column=1,padx=5)
        self.del_btn  = tk.Button(ctrl, text="✕ Elimina [D]",bg="#3a1a1a",fg=RED_C,command=self.delete,state=tk.DISABLED, **bst)
        self.del_btn.grid(row=0,column=2,padx=5)
        self.next_btn = tk.Button(ctrl, text="Succ ▶",      bg=BG3,fg=FG_MID,command=self.show_next,state=tk.DISABLED, **bst)
        self.next_btn.grid(row=0,column=3,padx=5)

        self.status_lbl = tk.Label(self.frame, text="Seleziona una cartella per iniziare.",
                                   font=("Courier",9), bg=BG, fg=FG_DIM)
        self.status_lbl.pack(pady=(0,6))

    # ── Zoom / Pan ────────────────────────────────────────
    def _on_scroll(self, e):
        if self._orig_pil is None: return
        delta = getattr(e, 'delta', 0)
        if delta == 0: delta = 120 if e.num == 4 else -120
        factor = 1.15 if delta > 0 else 1/1.15
        self._zoom = max(0.1, min(self._zoom * factor, 20.0))
        self._render_zoom()

    def _drag_start_fn(self, e):
        self._drag_start = (e.x, e.y)

    def _drag_move(self, e):
        if self._drag_start and self._orig_pil:
            dx = e.x - self._drag_start[0]; dy = e.y - self._drag_start[1]
            self._pan_x += dx; self._pan_y += dy
            self._drag_start = (e.x, e.y)
            self._render_zoom()

    def _zoom_reset(self, e=None):
        self._zoom=1.0; self._pan_x=0; self._pan_y=0; self._render_zoom()

    def _render_zoom(self):
        if self._orig_pil is None: return
        w = max(self.canvas.winfo_width(), 100); h = max(self.canvas.winfo_height(), 100)
        base_r = min(w/self._orig_pil.width, h/self._orig_pil.height)
        nw = max(1, int(self._orig_pil.width  * base_r * self._zoom))
        nh = max(1, int(self._orig_pil.height * base_r * self._zoom))
        img = self._orig_pil.resize((nw, nh), Image.LANCZOS)
        self.current_image = ImageTk.PhotoImage(img)
        self.canvas.delete("all")
        cx = w//2 + self._pan_x; cy = h//2 + self._pan_y
        self.canvas.create_image(cx, cy, image=self.current_image, anchor="center")
        self.canvas.image = self.current_image

    # ── Filtri ────────────────────────────────────────────
    def _apply_filters(self):
        if not self.all_files: return
        year_s = self.flt_year.get().strip()
        min_s  = self.flt_min.get().strip()
        max_s  = self.flt_max.get().strip()
        filt = []
        for fp in self.all_files:
            try:
                size_kb = os.path.getsize(fp) / 1024
                if min_s and size_kb < float(min_s): continue
                if max_s and size_kb > float(max_s): continue
                if year_s:
                    dt = get_file_date(fp)
                    if not dt or str(dt.year) != year_s: continue
                filt.append(fp)
            except Exception: continue
        self.photo_files = filt
        self.current_idx = 0 if filt else -1
        self.status_lbl.config(text=f"Filtro attivo: {len(filt)} foto")
        if filt: self._show(); self._upd_buttons()
        else: self._reset()

    def _reset_filters(self):
        self.flt_year.delete(0, tk.END); self.flt_min.delete(0, tk.END); self.flt_max.delete(0, tk.END)
        self.photo_files = list(self.all_files)
        self.current_idx = 0 if self.photo_files else -1
        if self.photo_files: self._show(); self._upd_buttons()

    # ── Confronto affiancato ──────────────────────────────
    def _open_compare(self):
        if len(self.photo_files) < 2:
            messagebox.showinfo("Info","Servono almeno 2 foto caricate."); return
        top = Toplevel(self.frame.winfo_toplevel())
        top.title("Confronto affiancato"); top.configure(bg=BG)
        top.geometry("1000x520")
        vars_ = [tk.StringVar(value=self.photo_files[min(i, len(self.photo_files)-1)]) for i in range(2)]
        imgs  = [None, None]
        labels = []

        def load_side(i):
            fp = vars_[i].get()
            try:
                img = Image.open(fp); img.thumbnail((460,420))
                ph  = ImageTk.PhotoImage(img); imgs[i]=ph
                labels[i].config(image=ph); labels[i].image=ph
            except Exception: pass

        for i in range(2):
            col = tk.Frame(top, bg=BG); col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=6, pady=6)
            fr  = tk.Frame(col, bg=BG); fr.pack(fill=tk.X)
            tk.Entry(fr, textvariable=vars_[i], font=("Courier",8), bg=BG3, fg=FG,
                     insertbackground=FG, relief=tk.FLAT).pack(side=tk.LEFT, fill=tk.X, expand=True)
            idx = i
            styled_button(fr,"📂", lambda ii=idx: (vars_[ii].set(filedialog.askopenfilename(
                filetypes=[("Immagini","*.jpg *.jpeg *.png *.bmp *.webp")]) or vars_[ii].get()),
                load_side(ii)), padx=4, pady=2).pack(side=tk.LEFT)
            lbl = tk.Label(col, bg=BG2); lbl.pack(fill=tk.BOTH, expand=True)
            labels.append(lbl)
            load_side(i)

    # ── Bind keys ─────────────────────────────────────────
    def _bind_keys(self):
        root = self.frame.winfo_toplevel()
        root.bind("<Left>",  lambda e: self.show_prev() if self.frame.winfo_ismapped() else None)
        root.bind("<Right>", lambda e: self.show_next() if self.frame.winfo_ismapped() else None)
        root.bind("<k>",     lambda e: self.keep()      if self.frame.winfo_ismapped() else None)
        root.bind("<K>",     lambda e: self.keep()      if self.frame.winfo_ismapped() else None)
        root.bind("<d>",     lambda e: self.delete()    if self.frame.winfo_ismapped() else None)
        root.bind("<D>",     lambda e: self.delete()    if self.frame.winfo_ismapped() else None)
        root.bind("<Configure>", self._on_resize)

    def _on_resize(self, e):
        if e.widget is self.frame.winfo_toplevel() and self.current_idx != -1: self._render_zoom()

    # ── Browse / Load ─────────────────────────────────────
    def browse(self):
        sel = filedialog.askdirectory()
        if not sel: return
        self.folder_path  = sel
        self.deleted_path = os.path.join(sel,"deleted_photos")
        os.makedirs(self.deleted_path, exist_ok=True)
        short = ("…"+sel[-47:]) if len(sel)>50 else sel
        self.folder_lbl.config(text=short); self._load()

    def _load(self):
        self.all_files   = collect_files(self.folder_path, IMAGE_EXTENSIONS, {self.deleted_path})
        self.photo_files = list(self.all_files)
        if not self.photo_files: self.status_lbl.config(text="Nessuna foto trovata."); self._reset(); return
        self.current_idx = 0; self._show(); self._upd_buttons()

    def _show(self):
        if not self.photo_files or self.current_idx==-1:
            self.canvas.delete("all"); self.current_image=None; self._orig_pil=None; return
        path = self.photo_files[self.current_idx]
        n, tot = self.current_idx+1, len(self.photo_files)
        try: rel = os.path.relpath(path, self.folder_path)
        except: rel = os.path.basename(path)
        size_kb = os.path.getsize(path)//1024
        self.fname_lbl.config(text=f"{rel}   ({size_kb} KB)")
        self.status_lbl.config(text=f"{n} / {tot}")
        self.pb.place(relwidth=n/tot, relheight=1)
        try:
            self._orig_pil = Image.open(path)
            self._zoom=1.0; self._pan_x=0; self._pan_y=0
            self.frame.winfo_toplevel().update_idletasks()
            self._render_zoom()
        except Exception as ex:
            messagebox.showerror("Errore", f"Impossibile caricare:\n{os.path.basename(path)}\n{ex}")
            self._remove_advance()

    def show_next(self):
        if self.current_idx < len(self.photo_files)-1:
            self.current_idx+=1; self._show(); self._upd_buttons()

    def show_prev(self):
        if self.current_idx>0:
            self.current_idx-=1; self._show(); self._upd_buttons()

    def keep(self):
        if not self.photo_files or self.current_idx==-1: return
        self.status_lbl.config(text=f"Tenuta: {os.path.basename(self.photo_files[self.current_idx])}")
        self._remove_advance()

    def delete(self):
        if not self.photo_files or self.current_idx==-1: return
        src = self.photo_files[self.current_idx]
        dst = unique_dest(self.deleted_path, os.path.basename(src))
        try:
            shutil.move(src, dst)
            self.all_files = [f for f in self.all_files if f!=src]
            self.status_lbl.config(text=f"Eliminata: {os.path.basename(src)}")
            self._remove_advance()
        except Exception as ex: messagebox.showerror("Errore", str(ex))

    def _remove_advance(self):
        self.photo_files.pop(self.current_idx)
        if not self.photo_files: self._done(); return
        if self.current_idx>=len(self.photo_files): self.current_idx=len(self.photo_files)-1
        self._show(); self._upd_buttons()

    def _done(self):
        self.current_idx=-1; self.canvas.delete("all"); self.current_image=None; self._orig_pil=None
        self.fname_lbl.config(text=""); self.pb.place(relwidth=1,relheight=1)
        self.status_lbl.config(text="✓ Tutte le foto elaborate!")
        self._upd_buttons(); messagebox.showinfo("Fine","Tutte le foto sono state processate!")

    def _upd_buttons(self):
        has = bool(self.photo_files)
        self.keep_btn.config(state=tk.NORMAL if has else tk.DISABLED)
        self.del_btn .config(state=tk.NORMAL if has else tk.DISABLED)
        self.prev_btn.config(state=tk.NORMAL if has and self.current_idx>0 else tk.DISABLED)
        self.next_btn.config(state=tk.NORMAL if has and self.current_idx<len(self.photo_files)-1 else tk.DISABLED)

    def _reset(self):
        self.photo_files=[]; self.all_files=[]; self.current_idx=-1
        self.current_image=None; self._orig_pil=None; self.canvas.delete("all")
        self.fname_lbl.config(text=""); self.pb.place(relwidth=0,relheight=1); self._upd_buttons()


# ══════════════════════════════════════════════════════════
#  TAB 2 — DUPLICATI
# ══════════════════════════════════════════════════════════
class DuplicatiTab:
    def __init__(self, nb):
        self.frame = tk.Frame(nb, bg=BG)
        nb.add(self.frame, text="  🔍 Duplicati  ")
        self._build()

    def _build(self):
        section_header(self.frame, "SCANSIONE DUPLICATI", "(perceptual hash)")
        body = tk.Frame(self.frame, bg=BG); body.pack(fill=tk.BOTH, expand=True, padx=14, pady=10)
        self.folder_var = tk.StringVar()
        folder_row(body, self.folder_var, "Cartella:").pack(fill=tk.X, pady=4)
        opts = tk.Frame(body, bg=BG); opts.pack(fill=tk.X, pady=4)
        tk.Label(opts, text="Soglia (0–20):", font=MONO, bg=BG, fg=FG_MID).pack(side=tk.LEFT)
        self.thresh_var = tk.IntVar(value=5)
        tk.Scale(opts, from_=0, to=20, orient=tk.HORIZONTAL, variable=self.thresh_var,
                 bg=BG, fg=FG, highlightthickness=0, troughcolor=BG3, length=180).pack(side=tk.LEFT, padx=4)
        tk.Label(opts, textvariable=self.thresh_var, font=MONO_B, bg=BG, fg=ACCENT, width=3).pack(side=tk.LEFT)
        self.sub_var = tk.BooleanVar(value=True)
        tk.Checkbutton(opts, text="Sottocartelle", variable=self.sub_var,
                       bg=BG, fg=FG_MID, selectcolor=BG3, activebackground=BG, font=MONO).pack(side=tk.LEFT, padx=16)
        lf, self.log = log_widget(body); lf.pack(fill=tk.BOTH, expand=True, pady=6)
        self.pb = ttk.Progressbar(body, orient="horizontal", mode="determinate")
        self.pb.pack(fill=tk.X, pady=(0,6))
        self.start_btn = styled_button(body,"▶  Avvia Scansione",self._start,color="#1a3a1a",fg=GREEN,padx=16,pady=8)
        self.start_btn.pack()

    def _log(self, msg):
        self.frame.after(0, lambda m=msg: (self.log.insert(tk.END, m+"\n"), self.log.see(tk.END)))

    def _start(self):
        folder = self.folder_var.get().strip()
        if not folder: messagebox.showerror("Errore","Scegli una cartella."); return
        self.log.delete(1.0, tk.END); self.start_btn.config(state=tk.DISABLED)
        threading.Thread(target=self._scan, args=(normalize(folder),), daemon=True).start()

    def _confirm(self, orig, dup, target):
        result=[]
        top=Toplevel(self.frame.winfo_toplevel()); top.title("Duplicato"); top.configure(bg=BG)
        top.transient(self.frame.winfo_toplevel()); top.grab_set(); top.resizable(False,False)
        def _mk(path, lbl_txt, col):
            try:
                img=Image.open(path); img.thumbnail((210,210)); ph=ImageTk.PhotoImage(img)
                l=tk.Label(pv,image=ph,bg=BG2); l.image=ph; l.grid(row=0,column=col,padx=6,pady=4)
            except: tk.Label(pv,text="⚠",bg=BG2,fg=RED_C,font=MONO).grid(row=0,column=col,padx=6)
            tk.Label(pv,text=lbl_txt,font=MONO,bg=BG2,fg=ACCENT).grid(row=1,column=col)
            tk.Label(pv,text=os.path.basename(path),font=("Courier",8),bg=BG2,fg=FG_DIM,wraplength=210).grid(row=2,column=col,padx=4)
        pv=tk.Frame(top,bg=BG2); pv.pack(padx=10,pady=10)
        _mk(orig,"ORIGINALE",0); _mk(dup,"DUPLICATO",1)
        bf=tk.Frame(top,bg=BG); bf.pack(pady=8)
        def act(v):
            if v=="sposta":
                os.makedirs(target,exist_ok=True)
                try: shutil.move(dup, unique_dest(target, os.path.basename(dup)))
                except Exception as ex: messagebox.showerror("Errore",str(ex),parent=top)
            elif v=="cestino":
                try: send2trash(dup)
                except Exception as ex: messagebox.showerror("Errore",str(ex),parent=top)
            result.append(v); top.destroy()
        styled_button(bf,"📦 Sposta",  lambda:act("sposta"), color="#2a2a00",fg=ACCENT,padx=12,pady=6).pack(side=tk.LEFT,padx=6)
        styled_button(bf,"🗑 Cestino", lambda:act("cestino"),color="#3a1a1a",fg=RED_C, padx=12,pady=6).pack(side=tk.LEFT,padx=6)
        styled_button(bf,"⭕ Lascia",  lambda:act("lascia"),                  padx=12,pady=6).pack(side=tk.LEFT,padx=6)
        def _center():
            top.update_idletasks(); root=self.frame.winfo_toplevel()
            top.geometry(f"+{root.winfo_x()+(root.winfo_width()-top.winfo_width())//2}+{root.winfo_y()+(root.winfo_height()-top.winfo_height())//2}")
        top.after(0,_center); self.frame.winfo_toplevel().wait_window(top)
        return result[0] if result else "lascia"

    def _scan(self, folder):
        _hash_cache.clear(); _res_cache.clear()
        target=os.path.join(folder,"duplicati_spostati")
        thresh=self.thresh_var.get(); sub=self.sub_var.get()
        all_f = collect_files(folder,IMAGE_EXTENSIONS,{normalize(target)}) if sub else [
            normalize(os.path.join(folder,f)) for f in os.listdir(folder)
            if Path(f).suffix.lower() in IMAGE_EXTENSIONS]
        total=len(all_f)
        self.frame.after(0,lambda:self.pb.config(maximum=max(total,1),value=0))
        self._log(f"Trovati {total} file.\n")
        hashes={}; moved=deleted=skipped=0
        for i,path in enumerate(all_f,1):
            self._log(f"[{i}/{total}]  {os.path.basename(path)}")
            self.frame.after(0,lambda v=i:self.pb.config(value=v))
            h=get_phash(path)
            if h is None: skipped+=1; self._log("  ↳ hash fallito"); continue
            matched=next((k for k in hashes if h-k<=thresh),None)
            if matched is None: hashes[h]=path; continue
            orig_c=hashes[matched]; orig=preferred_original(path,orig_c)
            dup=path if orig==orig_c else orig_c; hashes[matched]=orig
            self._log(f"  ⚠  simile a '{os.path.basename(orig)}' (diff={int(h-matched)})")
            action=self._confirm(orig,dup,target)
            if action=="sposta": moved+=1; self._log("  ➡ spostato")
            elif action=="cestino": deleted+=1; self._log("  🗑 cestino")
            else: skipped+=1; self._log("  ⭕ lasciato")
        self._log(f"\n✅ Fine — spostati:{moved}  cestino:{deleted}  saltati:{skipped}")
        self.frame.after(0,lambda:self.start_btn.config(state=tk.NORMAL))


# ══════════════════════════════════════════════════════════
#  TAB 3 — RIORDINA PER DATA
# ══════════════════════════════════════════════════════════
class RiordinaTab:
    def __init__(self, nb):
        self.frame = tk.Frame(nb, bg=BG)
        nb.add(self.frame, text="  📅 Riordina  ")
        self._build()

    def _build(self):
        section_header(self.frame,"RIORDINA PER DATA","(EXIF / mtime → Anno/Mese)")
        body=tk.Frame(self.frame,bg=BG); body.pack(fill=tk.BOTH,expand=True,padx=14,pady=10)
        self.src_var=tk.StringVar(); self.dst_var=tk.StringVar()
        folder_row(body,self.src_var,"Sorgente:").pack(fill=tk.X,pady=3)
        folder_row(body,self.dst_var,"Destinazione (vuota=stessa):").pack(fill=tk.X,pady=3)
        opts=tk.Frame(body,bg=BG); opts.pack(fill=tk.X,pady=6)
        self.op_var=tk.StringVar(value="sposta")
        for val,lbl in [("sposta","Sposta"),("copia","Copia")]:
            tk.Radiobutton(opts,text=lbl,variable=self.op_var,value=val,bg=BG,fg=FG_MID,
                           selectcolor=BG3,activebackground=BG,font=MONO).pack(side=tk.LEFT,padx=10)
        self.dry_var=tk.BooleanVar(value=True)
        tk.Checkbutton(opts,text="Dry-run (prova)",variable=self.dry_var,
                       bg=BG,fg=FG_MID,selectcolor=BG3,activebackground=BG,font=MONO).pack(side=tk.LEFT,padx=20)
        lf,self.log=log_widget(body); lf.pack(fill=tk.BOTH,expand=True,pady=6)
        self.pb=ttk.Progressbar(body,orient="horizontal",mode="determinate"); self.pb.pack(fill=tk.X,pady=(0,6))
        self.start_btn=styled_button(body,"▶  Avvia",self._start,color="#1a2a3a",fg=BLUE,padx=16,pady=8)
        self.start_btn.pack()

    def _log(self,msg): self.frame.after(0,lambda m=msg:(self.log.insert(tk.END,m+"\n"),self.log.see(tk.END)))

    def _start(self):
        src=self.src_var.get().strip()
        if not src: messagebox.showerror("Errore","Scegli la sorgente."); return
        dst=self.dst_var.get().strip() or src
        self.log.delete(1.0,tk.END); self.start_btn.config(state=tk.DISABLED)
        threading.Thread(target=self._run,args=(normalize(src),normalize(dst)),daemon=True).start()

    def _run(self,src,dst):
        sposta=self.op_var.get()=="sposta"; dry=self.dry_var.get()
        self._log(f"Modalità: {'DRY-RUN ' if dry else ''}{'SPOSTA' if sposta else 'COPIA'}\n")
        all_f=[str(f) for f in Path(src).rglob("*") if f.is_file()]
        total=len(all_f)
        self.frame.after(0,lambda:self.pb.config(maximum=max(total,1),value=0))
        ok=skip=err=0
        for i,fp in enumerate(sorted(all_f),1):
            self.frame.after(0,lambda v=i:self.pb.config(value=v))
            dt=get_file_date(fp)
            if not dt: self._log(f"  SALTA: {os.path.basename(fp)}"); skip+=1; continue
            dest_dir=Path(dst)/str(dt.year)/MESI_IT[dt.month]
            dest_f=dest_dir/Path(fp).name
            if dest_f.exists():
                base,ext=dest_f.stem,dest_f.suffix; j=1
                while dest_f.exists(): dest_f=dest_dir/f"{base} ({j}){ext}"; j+=1
            self._log(f"  {'[DRY] ' if dry else ''}→  {os.path.basename(fp)}  →  {dest_dir.relative_to(dst)}")
            if not dry:
                try:
                    dest_dir.mkdir(parents=True,exist_ok=True)
                    (shutil.move if sposta else shutil.copy2)(fp,dest_f); ok+=1
                except Exception as ex: self._log(f"    ✖ {ex}"); err+=1
            else: ok+=1
        self._log(f"\n✅ Fine — elaborati:{ok}  saltati:{skip}  errori:{err}")
        self.frame.after(0,lambda:self.start_btn.config(state=tk.NORMAL))


# ══════════════════════════════════════════════════════════
#  TAB 4 — SEPARA FILE
# ══════════════════════════════════════════════════════════
class SeparaTab:
    def __init__(self, nb):
        self.frame=tk.Frame(nb,bg=BG); nb.add(self.frame,text="  📂 Separa  "); self._build()

    def _build(self):
        section_header(self.frame,"SEPARA FOTO/VIDEO DAI JSON","(Google Takeout)")
        body=tk.Frame(self.frame,bg=BG); body.pack(fill=tk.BOTH,expand=True,padx=14,pady=10)
        self.folder_var=tk.StringVar()
        folder_row(body,self.folder_var,"Cartella Takeout:").pack(fill=tk.X,pady=4)
        tk.Label(body,text="Crea 'SOLO_FOTO' e 'SOLO_JSON'. Scansione ricorsiva.",
                 font=("Courier",9),bg=BG,fg=FG_DIM).pack(anchor="w",pady=4)
        lf,self.log=log_widget(body); lf.pack(fill=tk.BOTH,expand=True,pady=6)
        self.pb=ttk.Progressbar(body,orient="horizontal",mode="determinate"); self.pb.pack(fill=tk.X,pady=(0,6))
        styled_button(body,"▶  Avvia Separazione",self._start,color="#1a2a1a",fg=GREEN,padx=16,pady=8).pack()

    def _log(self,msg): self.frame.after(0,lambda m=msg:(self.log.insert(tk.END,m+"\n"),self.log.see(tk.END)))

    def _start(self):
        folder=self.folder_var.get().strip()
        if not folder: messagebox.showerror("Errore","Scegli una cartella."); return
        self.log.delete(1.0,tk.END)
        threading.Thread(target=self._run,args=(normalize(folder),),daemon=True).start()

    def _run(self,folder):
        fd=os.path.join(folder,"SOLO_FOTO"); jd=os.path.join(folder,"SOLO_JSON")
        os.makedirs(fd,exist_ok=True); os.makedirs(jd,exist_ok=True)
        media_ext=IMAGE_EXTENSIONS|VIDEO_EXTENSIONS; skip={normalize(fd),normalize(jd)}
        all_f=[]
        for rd,dirs,files in os.walk(folder):
            dirs[:]=[d for d in dirs if normalize(os.path.join(rd,d)) not in skip]
            for f in files: all_f.append(os.path.join(rd,f))
        total=len(all_f)
        self.frame.after(0,lambda:self.pb.config(maximum=max(total,1),value=0))
        foto=json_c=skip_c=0
        for i,fp in enumerate(all_f,1):
            self.frame.after(0,lambda v=i:self.pb.config(value=v))
            ext=Path(fp).suffix.lower()
            if ext in media_ext: shutil.move(fp,unique_dest(fd,os.path.basename(fp))); foto+=1
            elif ext==".json": shutil.move(fp,unique_dest(jd,os.path.basename(fp))); json_c+=1
            else: skip_c+=1
        self._log(f"✅ Fine — foto/video:{foto}  json:{json_c}  altri:{skip_c}")


# ══════════════════════════════════════════════════════════
#  TAB 5 — CONFRONTO CARTELLE
# ══════════════════════════════════════════════════════════
class ConfrontoTab:
    def __init__(self, nb):
        self.frame=tk.Frame(nb,bg=BG); nb.add(self.frame,text="  ⚖ Confronto  "); self._build()

    def _build(self):
        section_header(self.frame,"CONFRONTO TRA DUE CARTELLE","(MD5 pixel-perfetto)")
        body=tk.Frame(self.frame,bg=BG); body.pack(fill=tk.BOTH,expand=True,padx=14,pady=10)
        self.src_var=tk.StringVar(); self.dup_var=tk.StringVar()
        folder_row(body,self.src_var,"Cartella ORIGINALI:").pack(fill=tk.X,pady=3)
        folder_row(body,self.dup_var,"Cartella DUPLICATI:").pack(fill=tk.X,pady=3)
        tk.Label(body,text="Identici nella cartella DUPLICATI → cestino di sistema.",
                 font=("Courier",9),bg=BG,fg=FG_DIM).pack(anchor="w",pady=4)
        lf,self.log=log_widget(body); lf.pack(fill=tk.BOTH,expand=True,pady=6)
        self.pb=ttk.Progressbar(body,orient="horizontal",mode="determinate"); self.pb.pack(fill=tk.X,pady=(0,6))
        styled_button(body,"▶  Avvia Confronto",self._start,color="#3a1a1a",fg=RED_C,padx=16,pady=8).pack()

    def _log(self,msg): self.frame.after(0,lambda m=msg:(self.log.insert(tk.END,m+"\n"),self.log.see(tk.END)))

    def _img_hash(self,path):
        try:
            with Image.open(path) as img: return hashlib.md5(img.convert("RGB").tobytes()).hexdigest()
        except: return None

    def _start(self):
        src=self.src_var.get().strip(); dup=self.dup_var.get().strip()
        if not src or not dup: messagebox.showerror("Errore","Scegli entrambe le cartelle."); return
        self.log.delete(1.0,tk.END)
        threading.Thread(target=self._run,args=(normalize(src),normalize(dup)),daemon=True).start()

    def _run(self,src,dup):
        self._log("Scansione originali…")
        hashes={}
        for fp in collect_files(src,IMAGE_EXTENSIONS):
            h=self._img_hash(fp)
            if h: hashes[h]=fp
        self._log(f"Originali unici: {len(hashes)}\nScansione duplicati…")
        dup_files=collect_files(dup,IMAGE_EXTENSIONS); total=len(dup_files)
        self.frame.after(0,lambda:self.pb.config(maximum=max(total,1),value=0))
        trashed=0
        for i,fp in enumerate(dup_files,1):
            self.frame.after(0,lambda v=i:self.pb.config(value=v))
            h=self._img_hash(fp)
            if h and h in hashes:
                self._log(f"  🗑  {os.path.basename(fp)}")
                try: send2trash(fp); trashed+=1
                except Exception as ex: self._log(f"    ✖ {ex}")
        self._log(f"\n✅ Fine — {trashed} duplicati nel cestino.")


# ══════════════════════════════════════════════════════════
#  TAB 6 — ESTRAI VIDEO
# ══════════════════════════════════════════════════════════
class VideoTab:
    def __init__(self, nb):
        self.frame=tk.Frame(nb,bg=BG); nb.add(self.frame,text="  🎬 Video  "); self._build()

    def _build(self):
        section_header(self.frame,"ESTRAI VIDEO","(per cartella/sottocartella → VIDEO/)")
        body=tk.Frame(self.frame,bg=BG); body.pack(fill=tk.BOTH,expand=True,padx=14,pady=10)
        self.folder_var=tk.StringVar()
        folder_row(body,self.folder_var,"Cartella radice:").pack(fill=tk.X,pady=4)
        tk.Label(body,text="Per ogni directory con video crea la sottocartella VIDEO/ e sposta/copia i file.",
                 font=("Courier",9),bg=BG,fg=FG_DIM).pack(anchor="w",pady=4)
        opts=tk.Frame(body,bg=BG); opts.pack(fill=tk.X,pady=4)
        self.op_var=tk.StringVar(value="sposta")
        for val,lbl in [("sposta","Sposta"),("copia","Copia")]:
            tk.Radiobutton(opts,text=lbl,variable=self.op_var,value=val,bg=BG,fg=FG_MID,
                           selectcolor=BG3,activebackground=BG,font=MONO).pack(side=tk.LEFT,padx=10)
        lf,self.log=log_widget(body); lf.pack(fill=tk.BOTH,expand=True,pady=6)
        self.pb=ttk.Progressbar(body,orient="horizontal",mode="determinate"); self.pb.pack(fill=tk.X,pady=(0,6))
        styled_button(body,"▶  Avvia Estrazione",self._start,color="#1a1a3a",fg=BLUE,padx=16,pady=8).pack()

    def _log(self,msg): self.frame.after(0,lambda m=msg:(self.log.insert(tk.END,m+"\n"),self.log.see(tk.END)))

    def _start(self):
        folder=self.folder_var.get().strip()
        if not folder: messagebox.showerror("Errore","Scegli una cartella."); return
        self.log.delete(1.0,tk.END)
        threading.Thread(target=self._run,args=(normalize(folder),),daemon=True).start()

    def _run(self,root_folder):
        sposta=self.op_var.get()=="sposta"; VDN="VIDEO"
        all_v=[]
        for dp,dirs,files in os.walk(root_folder):
            dirs[:]=[d for d in dirs if d!=VDN]
            for f in files:
                if Path(f).suffix.lower() in VIDEO_EXTENSIONS: all_v.append(os.path.join(dp,f))
        total=len(all_v); self.frame.after(0,lambda:self.pb.config(maximum=max(total,1),value=0))
        if not total: self._log("Nessun video trovato."); return
        by_dir=defaultdict(list)
        for fp in all_v: by_dir[os.path.dirname(fp)].append(fp)
        moved=copied=err=0; proc=0
        for dp,files in by_dir.items():
            vd=os.path.join(dp,VDN); os.makedirs(vd,exist_ok=True)
            try: rel=os.path.relpath(dp,root_folder) or "."
            except: rel=dp
            self._log(f"\n📁  {rel}  →  {VDN}/")
            for fp in files:
                proc+=1; self.frame.after(0,lambda v=proc:self.pb.config(value=v))
                dst=unique_dest(vd,os.path.basename(fp))
                try:
                    if sposta: shutil.move(fp,dst); moved+=1
                    else: shutil.copy2(fp,dst); copied+=1
                    self._log(f"    {'→' if sposta else '⊕'}  {os.path.basename(fp)}")
                except Exception as ex: self._log(f"    ✖ {ex}"); err+=1
        self._log(f"\n✅ Fine — {'spostati' if sposta else 'copiati'}:{moved+copied}  errori:{err}")


# ══════════════════════════════════════════════════════════
#  TAB 7 — RINOMINA BATCH
# ══════════════════════════════════════════════════════════
class RinominaTab:
    """
    Pattern supportati:
      {YYYY} {MM} {DD} {hh} {mm} {ss}  ← data EXIF o mtime
      {n}    numero sequenziale (4 cifre)
      {name} nome originale senza estensione
      {ext}  estensione originale (con punto)
    """
    PATTERN_DEFAULT = "{YYYY}{MM}{DD}_{hh}{mm}{ss}_{n}"

    def __init__(self, nb):
        self.frame=tk.Frame(nb,bg=BG); nb.add(self.frame,text="  ✏ Rinomina  "); self._build()

    def _build(self):
        section_header(self.frame,"RINOMINA BATCH","(pattern personalizzato)")
        body=tk.Frame(self.frame,bg=BG); body.pack(fill=tk.BOTH,expand=True,padx=14,pady=10)
        self.folder_var=tk.StringVar()
        folder_row(body,self.folder_var,"Cartella:").pack(fill=tk.X,pady=4)

        pat_row=tk.Frame(body,bg=BG); pat_row.pack(fill=tk.X,pady=4)
        tk.Label(pat_row,text="Pattern:",font=MONO,bg=BG,fg=FG_MID,width=22,anchor="w").pack(side=tk.LEFT)
        self.pat_var=tk.StringVar(value=self.PATTERN_DEFAULT)
        tk.Entry(pat_row,textvariable=self.pat_var,font=MONO,bg=BG3,fg=FG,
                 insertbackground=FG,relief=tk.FLAT,bd=0).pack(side=tk.LEFT,fill=tk.X,expand=True)

        help_txt=("Variabili: {YYYY} {MM} {DD} {hh} {mm} {ss}  |  {n}=sequenza  |  {name}=nome orig.  |  {ext}=estensione\n"
                  "Es:  {YYYY}-{MM}-{DD}_{name}_{n}   →   2023-07-14_IMG_0042_0001.jpg")
        tk.Label(body,text=help_txt,font=("Courier",8),bg=BG,fg=FG_DIM,justify=tk.LEFT).pack(anchor="w",pady=4)

        opts=tk.Frame(body,bg=BG); opts.pack(fill=tk.X,pady=4)
        self.sub_var=tk.BooleanVar(value=False)
        tk.Checkbutton(opts,text="Includi sottocartelle",variable=self.sub_var,
                       bg=BG,fg=FG_MID,selectcolor=BG3,activebackground=BG,font=MONO).pack(side=tk.LEFT,padx=0)
        self.dry_var=tk.BooleanVar(value=True)
        tk.Checkbutton(opts,text="Dry-run (anteprima senza modificare)",variable=self.dry_var,
                       bg=BG,fg=FG_MID,selectcolor=BG3,activebackground=BG,font=MONO).pack(side=tk.LEFT,padx=20)

        lf,self.log=log_widget(body); lf.pack(fill=tk.BOTH,expand=True,pady=6)
        self.pb=ttk.Progressbar(body,orient="horizontal",mode="determinate"); self.pb.pack(fill=tk.X,pady=(0,6))
        self.start_btn=styled_button(body,"▶  Avvia Rinomina",self._start,
                                     color="#2a1a3a",fg=PURPLE,padx=16,pady=8)
        self.start_btn.pack()

    def _log(self,msg): self.frame.after(0,lambda m=msg:(self.log.insert(tk.END,m+"\n"),self.log.see(tk.END)))

    def _apply_pattern(self, pattern: str, path: str, seq: int, dt: Optional[datetime]) -> str:
        ext = Path(path).suffix
        name= Path(path).stem
        if dt:
            p=(pattern
               .replace("{YYYY}", f"{dt.year:04d}")
               .replace("{MM}",   f"{dt.month:02d}")
               .replace("{DD}",   f"{dt.day:02d}")
               .replace("{hh}",   f"{dt.hour:02d}")
               .replace("{mm}",   f"{dt.minute:02d}")
               .replace("{ss}",   f"{dt.second:02d}"))
        else:
            for tag in ["{YYYY}","{MM}","{DD}","{hh}","{mm}","{ss}"]:
                pattern=pattern.replace(tag,"xx")
            p=pattern
        p=p.replace("{n}",f"{seq:04d}").replace("{name}",name).replace("{ext}",ext)
        return p + ext

    def _start(self):
        folder=self.folder_var.get().strip()
        if not folder: messagebox.showerror("Errore","Scegli una cartella."); return
        pat=self.pat_var.get().strip()
        if not pat: messagebox.showerror("Errore","Inserisci un pattern."); return
        self.log.delete(1.0,tk.END); self.start_btn.config(state=tk.DISABLED)
        threading.Thread(target=self._run,args=(normalize(folder),pat),daemon=True).start()

    def _run(self, folder, pattern):
        dry=self.dry_var.get()
        sub=self.sub_var.get()
        files = collect_files(folder,IMAGE_EXTENSIONS) if sub else [
            normalize(os.path.join(folder,f)) for f in sorted(os.listdir(folder))
            if Path(f).suffix.lower() in IMAGE_EXTENSIONS and os.path.isfile(os.path.join(folder,f))]
        total=len(files)
        self.frame.after(0,lambda:self.pb.config(maximum=max(total,1),value=0))
        self._log(f"File trovati: {total}  |  Modalità: {'DRY-RUN' if dry else 'REALE'}\n")
        renamed=skipped=conflict=0
        for i,fp in enumerate(files,1):
            self.frame.after(0,lambda v=i:self.pb.config(value=v))
            dt=get_file_date(fp)
            new_name=self._apply_pattern(pattern,fp,i,dt)
            new_path=os.path.join(os.path.dirname(fp),new_name)
            self._log(f"  {os.path.basename(fp):<35}  →  {new_name}")
            if not dry:
                if os.path.exists(new_path) and new_path!=fp:
                    self._log(f"    ⚠ conflitto — saltato"); conflict+=1; continue
                try: os.rename(fp,new_path); renamed+=1
                except Exception as ex: self._log(f"    ✖ {ex}"); skipped+=1
            else: renamed+=1
        self._log(f"\n✅ Fine — {'rinominati' if not dry else 'da rinominare'}:{renamed}  conflitti:{conflict}  saltati:{skipped}")
        self.frame.after(0,lambda:self.start_btn.config(state=tk.NORMAL))


# ══════════════════════════════════════════════════════════
#  TAB 8 — RECUPERA DATE EXIF
# ══════════════════════════════════════════════════════════
class RecuperaExifTab:
    def __init__(self, nb):
        self.frame=tk.Frame(nb,bg=BG); nb.add(self.frame,text="  🗓 EXIF  "); self._build()

    def _build(self):
        section_header(self.frame,"RECUPERA DATE EXIF MANCANTI","(da nome file → metadati)")
        body=tk.Frame(self.frame,bg=BG); body.pack(fill=tk.BOTH,expand=True,padx=14,pady=10)
        self.folder_var=tk.StringVar()
        folder_row(body,self.folder_var,"Cartella:").pack(fill=tk.X,pady=4)

        info=(
            "Analizza ogni JPG senza data EXIF.\n"
            "Tenta di ricavare la data dal nome file (es. IMG_20230615_103020.jpg,\n"
            "2023-06-15, 20230615_103020, ecc.) e la scrive nei metadati DateTimeOriginal.\n"
            f"{'✅ piexif installato — scrittura EXIF abilitata.' if HAS_PIEXIF else '⚠ piexif non trovato — installa con: pip install piexif'}"
        )
        tk.Label(body,text=info,font=("Courier",9),bg=BG,fg=GREEN if HAS_PIEXIF else ACCENT,
                 justify=tk.LEFT).pack(anchor="w",pady=6)

        opts=tk.Frame(body,bg=BG); opts.pack(fill=tk.X,pady=4)
        self.sub_var=tk.BooleanVar(value=True)
        tk.Checkbutton(opts,text="Includi sottocartelle",variable=self.sub_var,
                       bg=BG,fg=FG_MID,selectcolor=BG3,activebackground=BG,font=MONO).pack(side=tk.LEFT)
        self.dry_var=tk.BooleanVar(value=True)
        tk.Checkbutton(opts,text="Dry-run",variable=self.dry_var,
                       bg=BG,fg=FG_MID,selectcolor=BG3,activebackground=BG,font=MONO).pack(side=tk.LEFT,padx=20)

        lf,self.log=log_widget(body); lf.pack(fill=tk.BOTH,expand=True,pady=6)
        self.pb=ttk.Progressbar(body,orient="horizontal",mode="determinate"); self.pb.pack(fill=tk.X,pady=(0,6))
        self.start_btn=styled_button(body,"▶  Avvia Recupero",self._start,
                                     color="#1a3a3a",fg="#6ec8c8",padx=16,pady=8)
        self.start_btn.pack()

    def _log(self,msg): self.frame.after(0,lambda m=msg:(self.log.insert(tk.END,m+"\n"),self.log.see(tk.END)))

    def _start(self):
        folder=self.folder_var.get().strip()
        if not folder: messagebox.showerror("Errore","Scegli una cartella."); return
        self.log.delete(1.0,tk.END); self.start_btn.config(state=tk.DISABLED)
        threading.Thread(target=self._run,args=(normalize(folder),),daemon=True).start()

    def _run(self,folder):
        dry=self.dry_var.get(); sub=self.sub_var.get()
        # Solo JPG/JPEG per scrittura EXIF
        ext_set={'.jpg','.jpeg'}
        files = collect_files(folder,ext_set) if sub else [
            normalize(os.path.join(folder,f)) for f in sorted(os.listdir(folder))
            if Path(f).suffix.lower() in ext_set and os.path.isfile(os.path.join(folder,f))]
        total=len(files)
        self.frame.after(0,lambda:self.pb.config(maximum=max(total,1),value=0))
        found=written=skipped=no_date=0
        for i,fp in enumerate(files,1):
            self.frame.after(0,lambda v=i:self.pb.config(value=v))
            existing=get_exif_date(fp)
            if existing: skipped+=1; continue  # ha già la data
            dt=date_from_filename(fp)
            if not dt:
                self._log(f"  ✗  {os.path.basename(fp):<40} — pattern non riconosciuto")
                no_date+=1; continue
            found+=1
            self._log(f"  {'[DRY] ' if dry else '✓'}  {os.path.basename(fp):<38}  →  {dt:%Y-%m-%d %H:%M:%S}")
            if not dry and HAS_PIEXIF:
                try:
                    import piexif
                    date_str=dt.strftime(EXIF_FMT).encode()
                    try: exif_dict=piexif.load(fp)
                    except: exif_dict={"0th":{},"Exif":{},"GPS":{},"1st":{}}
                    exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal]=date_str
                    exif_dict["Exif"][piexif.ExifIFD.DateTimeDigitized]=date_str
                    exif_dict["0th"][piexif.ImageIFD.DateTime]=date_str
                    piexif.insert(piexif.dump(exif_dict),fp)
                    written+=1
                except Exception as ex: self._log(f"    ✖ {ex}")
        self._log(f"\n✅ Fine — già con data:{skipped}  trovate:{found}  scritte:{written if not dry else '(dry)'}  pattern mancante:{no_date}")
        self.frame.after(0,lambda:self.start_btn.config(state=tk.NORMAL))


# ══════════════════════════════════════════════════════════
#  TAB 9 — DASHBOARD
# ══════════════════════════════════════════════════════════
class DashboardTab:
    def __init__(self, nb):
        self.frame=tk.Frame(nb,bg=BG); nb.add(self.frame,text="  📊 Dashboard  "); self._build()

    def _build(self):
        section_header(self.frame,"DASHBOARD","(statistiche raccolta foto)")
        top_ctrl=tk.Frame(self.frame,bg=BG); top_ctrl.pack(fill=tk.X,padx=14,pady=6)
        self.folder_var=tk.StringVar()
        folder_row(top_ctrl,self.folder_var,"Cartella:").pack(fill=tk.X)
        styled_button(top_ctrl,"📊  Analizza",self._start,color="#1a2a1a",fg=GREEN,padx=14,pady=6).pack(pady=6)

        self.scroll_canvas=tk.Canvas(self.frame,bg=BG,highlightthickness=0)
        sb=tk.Scrollbar(self.frame,orient="vertical",command=self.scroll_canvas.yview)
        self.scroll_canvas.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT,fill=tk.Y)
        self.scroll_canvas.pack(fill=tk.BOTH,expand=True,padx=14,pady=4)
        self.inner=tk.Frame(self.scroll_canvas,bg=BG)
        self.win_id=self.scroll_canvas.create_window((0,0),window=self.inner,anchor="nw")
        self.inner.bind("<Configure>",lambda e:self.scroll_canvas.configure(
            scrollregion=self.scroll_canvas.bbox("all")))
        self.scroll_canvas.bind("<Configure>",lambda e:self.scroll_canvas.itemconfig(self.win_id,width=e.width))

    def _start(self):
        folder=self.folder_var.get().strip()
        if not folder: messagebox.showerror("Errore","Scegli una cartella."); return
        for w in self.inner.winfo_children(): w.destroy()
        tk.Label(self.inner,text="Analisi in corso…",font=MONO,bg=BG,fg=FG_MID).pack(pady=20)
        threading.Thread(target=self._run,args=(normalize(folder),),daemon=True).start()

    def _run(self,folder):
        files=collect_files(folder,IMAGE_EXTENSIONS)
        by_year=defaultdict(int); by_month=defaultdict(int)
        by_cam=defaultdict(int); sizes=[]; total_bytes=0
        for fp in files:
            dt=get_file_date(fp)
            if dt:
                by_year[dt.year]+=1
                by_month[f"{dt.year}-{dt.month:02d}"]+=1
            cam=get_camera(fp); by_cam[cam]+=1
            try:
                s=os.path.getsize(fp); sizes.append(s); total_bytes+=s
            except: pass
        self.frame.after(0,lambda:self._render(files,by_year,by_month,by_cam,sizes,total_bytes))

    def _render(self,files,by_year,by_month,by_cam,sizes,total_bytes):
        for w in self.inner.winfo_children(): w.destroy()
        pad=dict(pady=2,padx=4,anchor="w")

        def section(title,color=ACCENT):
            tk.Label(self.inner,text=f"── {title} ──",font=MONO_B,bg=BG,fg=color).pack(fill=tk.X,padx=4,pady=(12,4))

        # Totali
        section("RIEPILOGO GENERALE")
        total_mb=total_bytes/1024/1024
        avg_kb=(sum(sizes)/len(sizes)/1024) if sizes else 0
        for txt in [f"  Foto totali:           {len(files)}",
                    f"  Spazio occupato:       {total_mb:.1f} MB",
                    f"  Dimensione media:      {avg_kb:.1f} KB"]:
            tk.Label(self.inner,text=txt,font=MONO,bg=BG,fg=FG_MID).pack(**pad)

        # Per anno
        if by_year:
            section("DISTRIBUZIONE PER ANNO",BLUE)
            max_y=max(by_year.values())
            for yr in sorted(by_year):
                canvas_bar(self.inner,str(yr),by_year[yr],max_y,BLUE).pack(**pad)

        # Per mese (ultimi 24)
        if by_month:
            section("DISTRIBUZIONE PER MESE (ultimi 24)",GREEN)
            sorted_m=sorted(by_month)[-24:]
            max_m=max(by_month[k] for k in sorted_m)
            for k in sorted_m:
                canvas_bar(self.inner,k,by_month[k],max_m,GREEN).pack(**pad)

        # Per fotocamera
        if by_cam:
            section("FOTOCAMERE UTILIZZATE",ACCENT)
            top_cam=sorted(by_cam.items(),key=lambda x:-x[1])[:15]
            max_c=top_cam[0][1]
            for cam,cnt in top_cam:
                canvas_bar(self.inner,cam[:26],cnt,max_c,ACCENT).pack(**pad)

        # Distribuzione dimensioni
        if sizes:
            section("DISTRIBUZIONE DIMENSIONE FILE",PURPLE)
            buckets=[(0,100,"<100 KB"),(100,500,"100–500 KB"),(500,2000,"500 KB–2 MB"),
                     (2000,10000,"2–10 MB"),(10000,999999,">10 MB")]
            max_b=1
            counts={}
            for lo,hi,lbl in buckets:
                c=sum(1 for s in sizes if lo*1024<=s<hi*1024)
                counts[lbl]=c; max_b=max(max_b,c)
            for _,_,lbl in buckets:
                canvas_bar(self.inner,lbl,counts[lbl],max_b,PURPLE).pack(**pad)

        self.scroll_canvas.yview_moveto(0)


# ══════════════════════════════════════════════════════════
#  TAB 10 — MAPPA GPS
# ══════════════════════════════════════════════════════════
class MappaTab:
    def __init__(self, nb):
        self.frame=tk.Frame(nb,bg=BG); nb.add(self.frame,text="  🗺 Mappa GPS  "); self._build()

    def _build(self):
        section_header(self.frame,"MAPPA GPS","(apre browser con coordinate EXIF)")
        body=tk.Frame(self.frame,bg=BG); body.pack(fill=tk.BOTH,expand=True,padx=14,pady=10)
        self.folder_var=tk.StringVar()
        folder_row(body,self.folder_var,"Cartella:").pack(fill=tk.X,pady=4)
        tk.Label(body,text="Legge le coordinate GPS dai metadati EXIF e genera una mappa HTML interattiva (OpenStreetMap).",
                 font=("Courier",9),bg=BG,fg=FG_DIM,wraplength=700).pack(anchor="w",pady=4)
        lf,self.log=log_widget(body); lf.pack(fill=tk.BOTH,expand=True,pady=6)
        self.pb=ttk.Progressbar(body,orient="horizontal",mode="determinate"); self.pb.pack(fill=tk.X,pady=(0,6))
        styled_button(body,"🗺  Genera Mappa",self._start,color="#1a2a2a",fg="#6ec8c8",padx=16,pady=8).pack()

    def _log(self,msg): self.frame.after(0,lambda m=msg:(self.log.insert(tk.END,m+"\n"),self.log.see(tk.END)))

    def _start(self):
        folder=self.folder_var.get().strip()
        if not folder: messagebox.showerror("Errore","Scegli una cartella."); return
        self.log.delete(1.0,tk.END)
        threading.Thread(target=self._run,args=(normalize(folder),),daemon=True).start()

    def _run(self,folder):
        files=collect_files(folder,IMAGE_EXTENSIONS); total=len(files)
        self.frame.after(0,lambda:self.pb.config(maximum=max(total,1),value=0))
        points=[]
        for i,fp in enumerate(files,1):
            self.frame.after(0,lambda v=i:self.pb.config(value=v))
            gps=get_gps(fp)
            if gps:
                lat,lon=gps
                self._log(f"  📍  {os.path.basename(fp):<40}  {lat:.5f}, {lon:.5f}")
                points.append((lat,lon,os.path.basename(fp)))
        if not points:
            self._log("Nessuna foto con coordinate GPS trovata."); return
        self._log(f"\n{len(points)} foto con GPS. Apertura mappa…")
        html=self._build_html(points)
        tmp=tempfile.NamedTemporaryFile(mode="w",suffix=".html",delete=False,encoding="utf-8")
        tmp.write(html); tmp.close()
        webbrowser.open(f"file://{tmp.name}")

    def _build_html(self, points):
        center_lat=sum(p[0] for p in points)/len(points)
        center_lon=sum(p[1] for p in points)/len(points)
        markers="\n".join(
            f'L.marker([{lat},{lon}]).addTo(map).bindPopup("<b>{name}</b><br>{lat:.5f}, {lon:.5f}");'
            for lat,lon,name in points)
        return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>body{{margin:0}}#map{{height:100vh}}</style></head>
<body><div id="map"></div><script>
var map=L.map('map').setView([{center_lat},{center_lon}],8);
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',
{{attribution:'© OpenStreetMap'}}).addTo(map);
{markers}
</script></body></html>"""


# ══════════════════════════════════════════════════════════
#  TAB 11 — FOTO SIMILI A RIFERIMENTO
# ══════════════════════════════════════════════════════════
class SimiliTab:
    def __init__(self, nb):
        self.frame=tk.Frame(nb,bg=BG); nb.add(self.frame,text="  🔎 Simili  "); self._build()
        self._results=[]; self._result_images=[]

    def _build(self):
        section_header(self.frame,"TROVA FOTO SIMILI","(rispetto a un'immagine di riferimento)")
        body=tk.Frame(self.frame,bg=BG); body.pack(fill=tk.BOTH,expand=True,padx=14,pady=10)
        self.ref_var=tk.StringVar(); self.folder_var=tk.StringVar()
        file_row(body,self.ref_var,"Foto di riferimento:").pack(fill=tk.X,pady=3)
        folder_row(body,self.folder_var,"Cerca in cartella:").pack(fill=tk.X,pady=3)

        opts=tk.Frame(body,bg=BG); opts.pack(fill=tk.X,pady=4)
        tk.Label(opts,text="Soglia (0=identica, 20=molto simile):",font=MONO,bg=BG,fg=FG_MID).pack(side=tk.LEFT)
        self.thresh_var=tk.IntVar(value=10)
        tk.Scale(opts,from_=0,to=40,orient=tk.HORIZONTAL,variable=self.thresh_var,
                 bg=BG,fg=FG,highlightthickness=0,troughcolor=BG3,length=180).pack(side=tk.LEFT,padx=4)
        tk.Label(opts,textvariable=self.thresh_var,font=MONO_B,bg=BG,fg=ACCENT,width=3).pack(side=tk.LEFT)
        self.max_var=tk.IntVar(value=20)
        tk.Label(opts,text="  Max risultati:",font=MONO,bg=BG,fg=FG_MID).pack(side=tk.LEFT,padx=(16,4))
        tk.Spinbox(opts,from_=1,to=200,textvariable=self.max_var,width=5,
                   bg=BG3,fg=FG,insertbackground=FG,font=MONO,relief=tk.FLAT).pack(side=tk.LEFT)

        self.pb=ttk.Progressbar(body,orient="horizontal",mode="determinate"); self.pb.pack(fill=tk.X,pady=4)
        self.status_lbl=tk.Label(body,text="",font=("Courier",9),bg=BG,fg=FG_MID)
        self.status_lbl.pack(anchor="w")

        styled_button(body,"🔎  Cerca",self._start,color="#2a1a2a",fg=PURPLE,padx=14,pady=6).pack(pady=4)

        # Griglia risultati con scroll
        res_outer=tk.Frame(body,bg=BG); res_outer.pack(fill=tk.BOTH,expand=True)
        self.res_canvas=tk.Canvas(res_outer,bg=BG,highlightthickness=0)
        sb=tk.Scrollbar(res_outer,orient="vertical",command=self.res_canvas.yview)
        self.res_canvas.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT,fill=tk.Y)
        self.res_canvas.pack(fill=tk.BOTH,expand=True)
        self.res_inner=tk.Frame(self.res_canvas,bg=BG)
        self.win_id=self.res_canvas.create_window((0,0),window=self.res_inner,anchor="nw")
        self.res_inner.bind("<Configure>",lambda e:self.res_canvas.configure(
            scrollregion=self.res_canvas.bbox("all")))
        self.res_canvas.bind("<Configure>",lambda e:self.res_canvas.itemconfig(self.win_id,width=e.width))

    def _start(self):
        ref=self.ref_var.get().strip(); folder=self.folder_var.get().strip()
        if not ref or not folder: messagebox.showerror("Errore","Scegli foto di riferimento e cartella."); return
        for w in self.res_inner.winfo_children(): w.destroy()
        self._result_images.clear()
        threading.Thread(target=self._run,args=(normalize(ref),normalize(folder)),daemon=True).start()

    def _run(self,ref,folder):
        ref_h=get_phash(ref)
        if ref_h is None:
            self.frame.after(0,lambda:messagebox.showerror("Errore","Impossibile calcolare hash della foto di riferimento.")); return
        files=collect_files(folder,IMAGE_EXTENSIONS); total=len(files)
        self.frame.after(0,lambda:self.pb.config(maximum=max(total,1),value=0))
        thresh=self.thresh_var.get(); max_r=self.max_var.get()
        results=[]
        for i,fp in enumerate(files,1):
            self.frame.after(0,lambda v=i:self.pb.config(value=v))
            if normalize(fp)==normalize(ref): continue
            h=get_phash(fp)
            if h is None: continue
            diff=int(ref_h-h)
            if diff<=thresh: results.append((diff,fp))
        results.sort(); results=results[:max_r]
        self.frame.after(0,lambda r=results:self._render_results(r))

    def _render_results(self,results):
        for w in self.res_inner.winfo_children(): w.destroy()
        self._result_images.clear()
        self.status_lbl.config(text=f"Trovati {len(results)} risultati.")
        if not results:
            tk.Label(self.res_inner,text="Nessuna foto simile trovata.",font=MONO,bg=BG,fg=FG_DIM).pack(pady=20)
            return
        cols=4; row_f=None
        for idx,(diff,fp) in enumerate(results):
            if idx%cols==0:
                row_f=tk.Frame(self.res_inner,bg=BG); row_f.pack(fill=tk.X,padx=4,pady=4)
            cell=tk.Frame(row_f,bg=BG2,bd=1,relief=tk.FLAT); cell.pack(side=tk.LEFT,padx=4,pady=2)
            try:
                img=Image.open(fp); img.thumbnail((150,120))
                ph=ImageTk.PhotoImage(img); self._result_images.append(ph)
                tk.Label(cell,image=ph,bg=BG2).pack()
            except:
                tk.Label(cell,text="⚠",bg=BG2,fg=RED_C,font=("Courier",20)).pack(padx=20,pady=20)
            name=os.path.basename(fp)
            name=name[:18]+"…" if len(name)>20 else name
            tk.Label(cell,text=f"{name}\ndiff={diff}",font=("Courier",8),bg=BG2,
                     fg=FG_DIM,justify=tk.CENTER).pack()
        self.res_canvas.yview_moveto(0)


# ══════════════════════════════════════════════════════════
#  TAB 12 — QUALITÀ FOTO
# ══════════════════════════════════════════════════════════
class QualitaTab:
    def __init__(self, nb):
        self.frame=tk.Frame(nb,bg=BG); nb.add(self.frame,text="  🔬 Qualità  "); self._build()
        self._preview_imgs=[]

    def _build(self):
        section_header(self.frame,"ANALISI QUALITÀ","(sfocate · burst · sottoesposte/sovraesposte)")
        body=tk.Frame(self.frame,bg=BG); body.pack(fill=tk.BOTH,expand=True,padx=14,pady=8)
        self.folder_var=tk.StringVar()
        folder_row(body,self.folder_var,"Cartella:").pack(fill=tk.X,pady=4)

        # Soglie
        thr=tk.Frame(body,bg=BG); thr.pack(fill=tk.X,pady=4)
        tk.Label(thr,text="Soglia sfocatura (var.Lap.):",font=MONO,bg=BG,fg=FG_MID).pack(side=tk.LEFT)
        self.blur_thr=tk.IntVar(value=50)
        tk.Scale(thr,from_=5,to=300,orient=tk.HORIZONTAL,variable=self.blur_thr,
                 bg=BG,fg=FG,highlightthickness=0,troughcolor=BG3,length=150).pack(side=tk.LEFT,padx=4)
        tk.Label(thr,textvariable=self.blur_thr,font=MONO_B,bg=BG,fg=ACCENT,width=4).pack(side=tk.LEFT)
        tk.Label(thr,text="  Soglia burst (sec):",font=MONO,bg=BG,fg=FG_MID).pack(side=tk.LEFT,padx=(16,4))
        self.burst_thr=tk.IntVar(value=2)
        tk.Spinbox(thr,from_=1,to=30,textvariable=self.burst_thr,width=4,
                   bg=BG3,fg=FG,insertbackground=FG,font=MONO,relief=tk.FLAT).pack(side=tk.LEFT)

        checks=tk.Frame(body,bg=BG); checks.pack(fill=tk.X,pady=4)
        self.do_blur=tk.BooleanVar(value=True)
        self.do_burst=tk.BooleanVar(value=True)
        self.do_exposure=tk.BooleanVar(value=True)
        for var,lbl in [(self.do_blur,"Sfocate/mosse"),(self.do_burst,"Burst identici"),(self.do_exposure,"Esposizione")]:
            tk.Checkbutton(checks,text=lbl,variable=var,bg=BG,fg=FG_MID,
                           selectcolor=BG3,activebackground=BG,font=MONO).pack(side=tk.LEFT,padx=8)

        self.pb=ttk.Progressbar(body,orient="horizontal",mode="determinate"); self.pb.pack(fill=tk.X,pady=4)

        styled_button(body,"🔬  Analizza",self._start,color="#2a1a1a",fg=RED_C,padx=14,pady=6).pack(pady=4)

        # Notebook risultati
        self.res_nb=ttk.Notebook(body); self.res_nb.pack(fill=tk.BOTH,expand=True,pady=4)
        self.tab_blur   =tk.Frame(self.res_nb,bg=BG); self.res_nb.add(self.tab_blur,   text="  😶 Sfocate  ")
        self.tab_burst  =tk.Frame(self.res_nb,bg=BG); self.res_nb.add(self.tab_burst,  text="  📸 Burst  ")
        self.tab_exp    =tk.Frame(self.res_nb,bg=BG); self.res_nb.add(self.tab_exp,    text="  ☀ Esposizione  ")
        self._lf_blur,  self._log_blur   = log_widget(self.tab_blur)
        self._lf_burst, self._log_burst  = log_widget(self.tab_burst)
        self._lf_exp,   self._log_exp    = log_widget(self.tab_exp)
        for lf in [self._lf_blur, self._lf_burst, self._lf_exp]: lf.pack(fill=tk.BOTH,expand=True)

        # Bottone cestino per ogni tab
        for log_w,tab in [(self._log_blur,self.tab_blur),(self._log_burst,self.tab_burst),(self._log_exp,self.tab_exp)]:
            styled_button(tab,"🗑  Invia selezionati nel cestino",
                          lambda lw=log_w:self._trash_from_log(lw),
                          color="#3a1a1a",fg=RED_C,padx=12,pady=4).pack(pady=4)

    def _log_to(self,widget,msg):
        self.frame.after(0,lambda w=widget,m=msg:(w.insert(tk.END,m+"\n"),w.see(tk.END)))

    def _start(self):
        folder=self.folder_var.get().strip()
        if not folder: messagebox.showerror("Errore","Scegli una cartella."); return
        for lw in [self._log_blur,self._log_burst,self._log_exp]: lw.delete(1.0,tk.END)
        threading.Thread(target=self._run,args=(normalize(folder),),daemon=True).start()

    def _run(self,folder):
        files=collect_files(folder,IMAGE_EXTENSIONS); total=len(files)
        self.frame.after(0,lambda:self.pb.config(maximum=max(total,1),value=0))
        blur_thr=self.blur_thr.get(); burst_sec=self.burst_thr.get()
        blur_list=[]; burst_dict=defaultdict(list); exp_list=[]

        for i,fp in enumerate(files,1):
            self.frame.after(0,lambda v=i:self.pb.config(value=v))
            # Sfocatura
            if self.do_blur.get():
                score=blur_score(fp)
                if 0<=score<blur_thr:
                    blur_list.append((score,fp))
                    self._log_to(self._log_blur, f"  [{score:6.1f}]  {fp}")
            # Burst
            if self.do_burst.get():
                dt=get_exif_date(fp)
                if dt:
                    key=dt.strftime("%Y%m%d_%H%M")
                    burst_dict[key].append((dt,fp))
            # Esposizione
            if self.do_exposure.get():
                mean,dark,bright=exposure_score(fp)
                if dark:  exp_list.append(fp); self._log_to(self._log_exp,f"  🌑 SCURA  [{mean:5.1f}]  {fp}")
                elif bright: exp_list.append(fp); self._log_to(self._log_exp,f"  ☀ SOVRA  [{mean:5.1f}]  {fp}")

        # Burst — raggruppa per minuto e filtra gruppi > 1
        if self.do_burst.get():
            burst_groups=0
            for key,items in sorted(burst_dict.items()):
                items.sort()
                groups=[items[0:1]]
                for dt,fp in items[1:]:
                    prev_dt=groups[-1][-1][0]
                    if (dt-prev_dt).total_seconds()<=burst_sec: groups[-1].append((dt,fp))
                    else: groups.append([(dt,fp)])
                for grp in groups:
                    if len(grp)>1:
                        burst_groups+=1
                        self._log_to(self._log_burst,f"\n  📸 Burst #{burst_groups}  ({len(grp)} foto, {key})")
                        for dt,fp in grp: self._log_to(self._log_burst,f"    {dt:%H:%M:%S}  {fp}")

        blur_list.sort()
        self._log_to(self._log_blur,  f"\n✅ Sfocate trovate: {len(blur_list)}")
        self._log_to(self._log_burst, f"\n✅ Analisi burst completata.")
        self._log_to(self._log_exp,   f"\n✅ Problemi esposizione: {len(exp_list)}")

    def _trash_from_log(self, log_widget):
        """Legge i path dal log (righe che contengono os.sep) e chiede conferma prima di mandare al cestino."""
        content=log_widget.get(1.0,tk.END)
        paths=[line.strip() for line in content.splitlines()
               if os.sep in line and os.path.isfile(line.strip())]
        paths=list(dict.fromkeys(paths))  # dedup preservando ordine
        if not paths: messagebox.showinfo("Info","Nessun path file trovato nel log."); return
        if not messagebox.askyesno("Conferma",f"Mandare {len(paths)} file nel cestino?"): return
        trashed=0
        for fp in paths:
            try: send2trash(fp); trashed+=1
            except Exception as ex: messagebox.showerror("Errore",f"{fp}\n{ex}")
        messagebox.showinfo("Fatto",f"{trashed} file nel cestino.")


# ══════════════════════════════════════════════════════════
#  APP PRINCIPALE
# ══════════════════════════════════════════════════════════
class FotoManagerApp:
    def __init__(self):
        self.root=tk.Tk(); self.root.title("FotoManager v2")
        self.root.geometry("1060x760"); self.root.minsize(860,580)
        self.root.configure(bg=BG)
        self._styles(); self._header(); self._notebook()

    def _styles(self):
        st=ttk.Style()
        try: st.theme_use("clam")
        except tk.TclError: pass
        st.configure("TNotebook",background=BG,borderwidth=0)
        st.configure("TNotebook.Tab",background=BG3,foreground=FG_MID,
                     font=("Courier",9,"bold"),padding=[10,5])
        st.map("TNotebook.Tab",background=[("selected",BG2)],foreground=[("selected",ACCENT)])
        st.configure("TFrame",background=BG)
        st.configure("Horizontal.TProgressbar",troughcolor=BG3,background=ACCENT,thickness=4,borderwidth=0)

    def _header(self):
        hdr=tk.Frame(self.root,bg="#0e0e0e",height=38); hdr.pack(fill=tk.X); hdr.pack_propagate(False)
        tk.Label(hdr,text="◈  FOTO MANAGER  v2",font=("Courier",13,"bold"),
                 bg="#0e0e0e",fg=ACCENT).pack(side=tk.LEFT,padx=16,pady=8)
        tk.Label(hdr,text="Suite completa per la gestione fotografica",
                 font=("Courier",9),bg="#0e0e0e",fg=FG_DIM).pack(side=tk.LEFT,padx=4)

    def _notebook(self):
        nb=ttk.Notebook(self.root); nb.pack(fill=tk.BOTH,expand=True)
        VisualizzaTab(nb)
        DuplicatiTab(nb)
        RiordinaTab(nb)
        SeparaTab(nb)
        ConfrontoTab(nb)
        VideoTab(nb)
        RinominaTab(nb)
        RecuperaExifTab(nb)
        DashboardTab(nb)
        MappaTab(nb)
        SimiliTab(nb)
        QualitaTab(nb)

    def run(self): self.root.mainloop()


if __name__ == "__main__":
    FotoManagerApp().run()
