                """
LocalTune — reproductor local estilo Spotify
Compatible con Python 3.14+
Requiere:  pip install pygame mutagen pillow
"""

# ── Python 3.14: anotaciones lazy por defecto, 'type' keyword nativo,
#    X|Y unions sin imports, tomllib en stdlib, etc.

from __future__ import annotations   # garantiza compat en 3.10-3.13 también

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser, simpledialog
import os
import threading
import time
import random
import json
import io

import pygame
from mutagen import File as MutagenFile
from mutagen.id3 import ID3, APIC
from PIL import Image, ImageTk, ImageDraw

# ══════════════════════════════════════════════════════════════
#                          PYGAME AUDIO
# ══════════════════════════════════════════════════════════════
pygame.mixer.pre_init(44100, -16, 2, 2048)
pygame.mixer.init()

# ══════════════════════════════════════════════════════════════
#                                  TEMA
# ══════════════════════════════════════════════════════════════
T: dict[str, str] = {
    "BG_DARK":    "#0D0D0D",
    "BG_PANEL":   "#141414",
    "BG_CARD":    "#1A1A1A",
    "BG_HOVER":   "#242424",
    "ACCENT":     "#87cefa",
    "ACCENT2":    "#c1c1c1",
    "TEXT_MAIN":  "#FFFFFF",
    "TEXT_SUB":   "#A0A0A0",
    "TEXT_MUTED": "#535353",
    "SLIDER_BG":  "#404040",
}

SUPPORTED_AUDIO: tuple[str, ...] = (
    ".mp3", ".flac", ".wav", ".ogg", ".aac", ".m4a", ".opus", ".wma"
)
SUPPORTED_VIDEO: tuple[str, ...] = (
    ".mp4", ".mkv", ".avi", ".mov", ".webm", ".wmv"
)
SUPPORTED_ALL: tuple[str, ...] = SUPPORTED_AUDIO + SUPPORTED_VIDEO

F_TITLE  = ("Helvetica", 22, "bold")
F_SONG   = ("Helvetica", 13, "bold")
F_ARTIST = ("Helvetica", 11)
F_SMALL  = ("Helvetica", 9)
F_NAV    = ("Helvetica", 12, "bold")
F_BTN    = ("Helvetica", 18, "bold")

DATA_FILE: str = os.path.join(os.path.expanduser("~"), ".localtune_data.json")

# ══════════════════════════════════════════════════════════════
#          TYPE ALIASES  (sintaxis 'type' disponible desde Python 3.12)
# ══════════════════════════════════════════════════════════════
type Song      = dict[str, object]
type PlaylistMap = dict[str, list[int]]

# ══════════════════════════════════════════════════════════════
#                          ESTADO CENTRAL
# ══════════════════════════════════════════════════════════════
class State:
    songs:         list[Song]    = []
    playlists:     PlaylistMap   = {}
    current_index: int           = -1
    is_playing:    bool          = False
    is_shuffled:   bool          = False
    repeat_mode:   str           = "none"   # none | all | one
    volume:        float         = 0.70
    song_length:   float         = 0.0
    play_start:    float         = 0.0
    play_offset:   float         = 0.0
    view_indices:  list[int]     = []
    _saved_vol:    float         = 0.70

S = State()

# ══════════════════════════════════════════════════════════════
#                                  PERSISTENCIA
# ══════════════════════════════════════════════════════════════
def save_data() -> None:
    data = {
        "songs": [
            {k: v for k, v in song.items() if k != "cover_photo"}
            for song in S.songs
        ],
        "playlists": S.playlists,
        "volume": S.volume,
    }
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError:
        pass

def load_data() -> None:
    if not os.path.exists(DATA_FILE):
        return
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data: dict = json.load(f)
        for s in data.get("songs", []):
            if os.path.exists(s.get("path", "")):
                s.setdefault("liked", False)
                s.setdefault("cover_path", None)
                S.songs.append(s)
        S.playlists = data.get("playlists", {})
        S.volume    = float(data.get("volume", 0.70))
    except (OSError, json.JSONDecodeError, KeyError):
        pass

# ══════════════════════════════════════════════════════════════
#                                  HELPERS
# ══════════════════════════════════════════════════════════════
def fmt(secs: float) -> str:
    secs = max(0, int(secs))
    return f"{secs // 60}:{secs % 60:02d}"

def read_meta(path: str) -> Song:
    title  = os.path.splitext(os.path.basename(path))[0]
    artist = "Artista desconocido"
    album  = "Álbum desconocido"
    dur    = 0.0
    try:
        f = MutagenFile(path, easy=True)
        if f:
            title  = str(f.get("title",  [title])[0])
            artist = str(f.get("artist", [artist])[0])
            album  = str(f.get("album",  [album])[0])
            if hasattr(f.info, "length"):
                dur = float(f.info.length)
    except Exception:
        pass
    return {
        "path": path, "title": title, "artist": artist,
        "album": album, "duration": dur,
        "liked": False, "cover_path": None,
    }

def embedded_cover(path: str) -> ImageTk.PhotoImage | None:
    try:
        tags = ID3(path)
        for tag in tags.values():
            if isinstance(tag, APIC):
                img = Image.open(io.BytesIO(tag.data)).resize((220, 220), Image.LANCZOS)
                return ImageTk.PhotoImage(img)
    except Exception:
        pass
    return None

def default_cover() -> ImageTk.PhotoImage:
    img  = Image.new("RGB", (220, 220), T["BG_CARD"])
    draw = ImageDraw.Draw(img)
    draw.ellipse([30, 30, 190, 190],
                 fill=T["BG_HOVER"], outline=T["ACCENT"], width=2)
    draw.ellipse([98, 98, 122, 122], fill=T["ACCENT"])
    return ImageTk.PhotoImage(img)

def photo_from_file(path: str, size: tuple[int, int] = (220, 220)) -> ImageTk.PhotoImage:
    img = Image.open(path).resize(size, Image.LANCZOS)
    return ImageTk.PhotoImage(img)

# ══════════════════════════════════════════════════════════════
#                          REPRODUCCIÓN
# ══════════════════════════════════════════════════════════════
def load_and_play(idx: int, offset: float = 0.0) -> None:
    if not (0 <= idx < len(S.songs)):
        return
    S.current_index = idx
    song = S.songs[idx]

    ext = os.path.splitext(song["path"])[1].lower()
    if ext not in SUPPORTED_AUDIO:
        messagebox.showinfo("Video",
            f"Reproducción de video no disponible aún.\n{song['title']}")
        return

    try:
        pygame.mixer.music.load(str(song["path"]))
        pygame.mixer.music.set_volume(S.volume)
        pygame.mixer.music.play(start=float(offset))
    except Exception as e:
        messagebox.showerror("Error al reproducir", str(e))
        return

    S.is_playing  = True
    S.play_start  = time.monotonic()
    S.play_offset = offset
    S.song_length = float(song["duration"]) or 300.0

    # actualizar UI
    v_title.set(str(song["title"]))
    v_artist.set(str(song["artist"]))
    v_total.set(fmt(S.song_length))
    btn_play.config(text="⏸")
    btn_like.config(
        text="❤" if song.get("liked") else "♡",
        fg=T["ACCENT"] if song.get("liked") else T["TEXT_MUTED"],
    )
    _update_cover(song)
    _refresh_list(select=idx)

def _update_cover(song: Song) -> None:
    photo: ImageTk.PhotoImage | None = None
    cover_path = song.get("cover_path")
    if cover_path and os.path.exists(str(cover_path)):
        try:
            photo = photo_from_file(str(cover_path))
        except Exception:
            pass
    if photo is None:
        photo = embedded_cover(str(song["path"]))
    if photo is None:
        photo = default_cover()
    song["cover_photo"] = photo          # type: ignore[assignment]
    cover_lbl.config(image=photo)
    cover_lbl.image = photo              # type: ignore[attr-defined]

def play_pause() -> None:
    if not S.songs:
        return
    if S.current_index == -1:
        target = S.view_indices[0] if S.view_indices else 0
        load_and_play(target)
        return
    if S.is_playing:
        pygame.mixer.music.pause()
        S.play_offset += time.monotonic() - S.play_start
        S.is_playing = False
        btn_play.config(text="▶")
    else:
        pygame.mixer.music.unpause()
        S.play_start = time.monotonic()
        S.is_playing = True
        btn_play.config(text="⏸")

def next_track(*_) -> None:
    if not S.songs:
        return
    pool = S.view_indices or list(range(len(S.songs)))
    if not pool:
        return
    if S.repeat_mode == "one":
        load_and_play(S.current_index)
        return
    if S.is_shuffled:
        nxt = random.choice(pool)
    else:
        pos = pool.index(S.current_index) if S.current_index in pool else -1
        nxt = pool[(pos + 1) % len(pool)]
    load_and_play(nxt)

def prev_track(*_) -> None:
    if not S.songs:
        return
    elapsed = S.play_offset + (
        time.monotonic() - S.play_start if S.is_playing else 0
    )
    if elapsed > 3.0:
        load_and_play(S.current_index)
        return
    pool = S.view_indices or list(range(len(S.songs)))
    if not pool:
        return
    pos = pool.index(S.current_index) if S.current_index in pool else 1
    prv = pool[(pos - 1) % len(pool)]
    load_and_play(prv)

def seek_to(val: float) -> None:
    if S.song_length > 0 and S.current_index != -1:
        offset = (float(val) / 100.0) * S.song_length
        load_and_play(S.current_index, offset)

def set_volume(val: float) -> None:
    S.volume = float(val) / 100.0
    pygame.mixer.music.set_volume(S.volume)
    icon = "🔇" if S.volume == 0 else ("🔉" if S.volume < 0.4 else "🔊")
    lbl_vol_icon.config(text=icon)

def toggle_mute(*_) -> None:
    if S.volume > 0:
        S._saved_vol = S.volume
        v_vol.set(0)
        set_volume(0)
    else:
        restored = getattr(S, "_saved_vol", 0.7)
        v_vol.set(restored * 100)
        set_volume(restored * 100)

def toggle_shuffle() -> None:
    S.is_shuffled = not S.is_shuffled
    btn_shuf.config(fg=T["ACCENT"] if S.is_shuffled else T["TEXT_MUTED"])

def toggle_repeat() -> None:
    modes  = ["none", "all", "one"]
    icons  = {"none": "🔁", "all": "🔁",  "one": "🔂"}
    colors = {"none": T["TEXT_MUTED"], "all": T["ACCENT"], "one": T["ACCENT"]}
    S.repeat_mode = modes[(modes.index(S.repeat_mode) + 1) % 3]
    btn_rep.config(text=icons[S.repeat_mode], fg=colors[S.repeat_mode])

def toggle_like() -> None:
    if S.current_index == -1:
        return
    song = S.songs[S.current_index]
    song["liked"] = not bool(song.get("liked"))
    btn_like.config(
        text="❤" if song["liked"] else "♡",
        fg=T["ACCENT"] if song["liked"] else T["TEXT_MUTED"],
    )
    save_data()
    _refresh_list()

# ══════════════════════════════════════════════════════════════
#                              BIBLIOTECA
# ══════════════════════════════════════════════════════════════
def import_files() -> None:
    paths = filedialog.askopenfilenames(
        title="Importar archivos de audio / video",
        filetypes=[
            ("Medios soportados",
             " ".join(f"*{e}" for e in SUPPORTED_ALL)),
            ("Audio",
             " ".join(f"*{e}" for e in SUPPORTED_AUDIO)),
            ("Video",
             " ".join(f"*{e}" for e in SUPPORTED_VIDEO)),
            ("Todos los archivos", "*.*"),
        ],
    )
    added = 0
    for p in paths:
        if not any(s["path"] == p for s in S.songs):
            S.songs.append(read_meta(p))
            added += 1
    if added:
        apply_filter()
        save_data()

def import_folder() -> None:
    folder = filedialog.askdirectory(title="Importar carpeta de música")
    if not folder:
        return
    added = 0
    for root_dir, _, files in os.walk(folder):
        for fname in sorted(files):
            if os.path.splitext(fname)[1].lower() in SUPPORTED_ALL:
                p = os.path.join(root_dir, fname)
                if not any(s["path"] == p for s in S.songs):
                    S.songs.append(read_meta(p))
                    added += 1
    if added:
        apply_filter()
        save_data()
        messagebox.showinfo("Importar carpeta",
                            f"Se importaron {added} archivo(s).")

def remove_selected() -> None:
    sel = listbox.curselection()
    if not sel:
        return
    real_idx: int = (S.view_indices[sel[0]]
                     if S.view_indices else sel[0])
    if real_idx == S.current_index:
        pygame.mixer.music.stop()
        S.is_playing    = False
        S.current_index = -1
        btn_play.config(text="▶")
        v_title.set("Sin canción seleccionada")
        v_artist.set("—")
    S.songs.pop(real_idx)
    # reparar índices de playlists
    new_pl: PlaylistMap = {}
    for name, idxs in S.playlists.items():
        new_pl[name] = [
            i - (1 if i > real_idx else 0)
            for i in idxs if i != real_idx
        ]
    S.playlists = new_pl
    if S.current_index > real_idx:
        S.current_index -= 1
    apply_filter()
    save_data()

def set_cover_for_song() -> None:
    target = S.current_index
    sel = listbox.curselection()
    if sel:
        target = S.view_indices[sel[0]] if S.view_indices else sel[0]
    if target == -1:
        messagebox.showwarning("Portada",
                               "Selecciona primero una canción.")
        return
    path = filedialog.askopenfilename(
        title="Seleccionar imagen de portada",
        filetypes=[
            ("Imágenes", "*.jpg *.jpeg *.png *.webp *.bmp *.gif"),
            ("Todos los archivos", "*.*"),
        ],
    )
    if not path:
        return
    S.songs[target]["cover_path"] = path
    if target == S.current_index:
        _update_cover(S.songs[target])
    save_data()

# ══════════════════════════════════════════════════════════════
#                      BÚSQUEDA / FILTRO
# ══════════════════════════════════════════════════════════════
_SEARCH_PH = "  🔍  Buscar en tu biblioteca…"

def apply_filter(*_) -> None:
    q = v_search.get().strip().lower()
    if q and q != _SEARCH_PH.lower():
        S.view_indices = [
            i for i, s in enumerate(S.songs)
            if q in str(s["title"]).lower()
            or q in str(s["artist"]).lower()
            or q in str(s["album"]).lower()
        ]
    else:
        S.view_indices = list(range(len(S.songs)))
    _refresh_list()

def show_library() -> None:
    S.view_indices = list(range(len(S.songs)))
    lbl_section.config(text="Tu Biblioteca")
    _refresh_list()

def show_favorites() -> None:
    S.view_indices = [i for i, s in enumerate(S.songs)
                      if s.get("liked")]
    lbl_section.config(text="❤  Favoritos")
    _refresh_list()

# ══════════════════════════════════════════════════════════════
#                              PLAYLISTS
# ══════════════════════════════════════════════════════════════
def new_playlist() -> None:
    name = simpledialog.askstring(
        "Nueva playlist", "Nombre de la playlist:", parent=root
    )
    if not name or not name.strip():
        return
    name = name.strip()
    if name in S.playlists:
        messagebox.showwarning("Playlist", f'"{name}" ya existe.')
        return
    S.playlists[name] = []
    _add_playlist_btn(name)
    save_data()

def _add_playlist_btn(name: str) -> None:
    btn = tk.Button(
        frame_playlists,
        text=f"  ♪  {name}",
        font=F_ARTIST,
        bg=T["BG_PANEL"], fg=T["TEXT_SUB"],
        bd=0, relief="flat",
        activebackground=T["BG_HOVER"],
        activeforeground=T["TEXT_MAIN"],
        anchor="w", padx=16, pady=5,
        cursor="hand2",
        command=lambda n=name: _load_playlist(n),
    )
    btn.pack(fill="x")
                                                        # Clic derecho → eliminar
    btn.bind("<Button-3>",
             lambda e, n=name, b=btn: _delete_playlist(n, b))

def _load_playlist(name: str) -> None:
    idxs = S.playlists.get(name, [])
    S.view_indices = [i for i in idxs if 0 <= i < len(S.songs)]
    lbl_section.config(text=f"♪  {name}")
    _refresh_list()

def _delete_playlist(name: str, widget: tk.Widget) -> None:
    if messagebox.askyesno("Eliminar playlist",
                           f'¿Eliminar la playlist "{name}"?'):
        del S.playlists[name]
        widget.destroy()
        save_data()

def add_to_playlist() -> None:
    sel = listbox.curselection()
    real_idx: int = (
        S.view_indices[sel[0]] if sel and S.view_indices
        else S.current_index
    )
    if real_idx == -1:
        messagebox.showwarning("Playlist",
                               "Selecciona primero una canción.")
        return
    if not S.playlists:
        if messagebox.askyesno("Playlist",
                               "No tienes playlists.\n¿Crear una ahora?"):
            new_playlist()
        return

    win = tk.Toplevel(root)
    win.title("Agregar a playlist")
    win.geometry("300x340")
    win.configure(bg=T["BG_PANEL"])
    win.grab_set()

    tk.Label(win, text="Selecciona una playlist:",
             font=F_NAV, bg=T["BG_PANEL"],
             fg=T["TEXT_MAIN"]).pack(pady=14)

    lb = tk.Listbox(
        win, bg=T["BG_DARK"], fg=T["TEXT_MAIN"],
        font=F_ARTIST, bd=0, relief="flat",
        highlightthickness=0,
        selectbackground=T["BG_HOVER"],
        activestyle="none",
    )
    lb.pack(fill="both", expand=True, padx=16)
    for n in S.playlists:
        lb.insert(tk.END, f"  {n}")

    def confirm() -> None:
        sel2 = lb.curselection()
        if not sel2:
            return
        pl_name = list(S.playlists.keys())[sel2[0]]
        if real_idx not in S.playlists[pl_name]:
            S.playlists[pl_name].append(real_idx)
            save_data()
            messagebox.showinfo("Playlist",
                                f'Canción agregada a "{pl_name}".')
        else:
            messagebox.showinfo("Playlist", "Ya está en esa playlist.")
        win.destroy()

    tk.Button(win, text="Agregar", font=F_NAV,
              bg=T["ACCENT"], fg="#000",
              bd=0, relief="flat", padx=16, pady=6,
              cursor="hand2", command=confirm).pack(pady=12)

# ══════════════════════════════════════════════════════════════
#                             COLA
# ══════════════════════════════════════════════════════════════
def open_queue() -> None:
    win = tk.Toplevel(root)
    win.title("Cola de reproducción")
    win.geometry("420x500")
    win.configure(bg=T["BG_PANEL"])

    tk.Label(win, text="Cola de reproducción",
             font=F_TITLE, bg=T["BG_PANEL"],
             fg=T["TEXT_MAIN"]).pack(pady=14)

    sb = tk.Scrollbar(win)
    sb.pack(side="right", fill="y")
    lb = tk.Listbox(
        win, bg=T["BG_DARK"], fg=T["TEXT_MAIN"],
        font=F_ARTIST, bd=0, relief="flat",
        highlightthickness=0,
        selectbackground=T["BG_HOVER"],
        activestyle="none",
        yscrollcommand=sb.set,
    )
    lb.pack(fill="both", expand=True, padx=16, pady=8)
    sb.config(command=lb.yview)

    pool = S.view_indices or list(range(len(S.songs)))
    if S.current_index in pool:
        start = pool.index(S.current_index)
        order = pool[start:] + pool[:start]
    else:
        order = pool

    for ri in order:
        s = S.songs[ri]
        lb.insert(tk.END,
                  f"  {s['title']}   —   {s['artist']}")
        if ri == S.current_index:
            lb.itemconfig(tk.END, fg=T["ACCENT"])

    def on_dbl(e: tk.Event) -> None:                      # type: ignore[type-arg]
        sel2 = lb.curselection()
        if sel2:
            load_and_play(order[sel2[0]])
            win.destroy()

    lb.bind("<Double-Button-1>", on_dbl)

# ══════════════════════════════════════════════════════════════
#                                                                                  ECUALIZADOR
# ══════════════════════════════════════════════════════════════
def open_equalizer() -> None:
    win = tk.Toplevel(root)
    win.title("Ecualizador")
    win.geometry("540x300")
    win.configure(bg=T["BG_PANEL"])

    tk.Label(win, text="🎛  Ecualizador",
             font=F_TITLE, bg=T["BG_PANEL"],
             fg=T["TEXT_MAIN"]).pack(pady=12)

    bands = ["60Hz", "170Hz", "310Hz", "600Hz", "1kHz",
             "3kHz", "6kHz", "12kHz", "14kHz", "16kHz"]
    sf = tk.Frame(win, bg=T["BG_PANEL"])
    sf.pack(expand=True)

    for band in bands:
        col = tk.Frame(sf, bg=T["BG_PANEL"])
        col.pack(side="left", padx=5)
        var = tk.DoubleVar(value=0)
        ttk.Scale(col, from_=12, to=-12, variable=var,
                  orient="vertical", length=130).pack()
        tk.Label(col, text=band, font=F_SMALL,
                 bg=T["BG_PANEL"],
                 fg=T["TEXT_MUTED"]).pack()

    tk.Label(
        win,
        text="Para EQ real conecta con librería DSP (ej. pedalboard)",
        font=F_SMALL, bg=T["BG_PANEL"], fg=T["TEXT_MUTED"],
    ).pack(pady=6)

# ══════════════════════════════════════════════════════════════
#                          INFO DE CANCIÓN
# ══════════════════════════════════════════════════════════════
def song_info() -> None:
    if S.current_index == -1:
        messagebox.showinfo("Info", "No hay canción en reproducción.")
        return
    s = S.songs[S.current_index]
    win = tk.Toplevel(root)
    win.title("Información de canción")
    win.geometry("420x300")
    win.configure(bg=T["BG_PANEL"])

    tk.Label(win, text="ℹ  Información",
             font=F_TITLE, bg=T["BG_PANEL"],
             fg=T["TEXT_MAIN"]).pack(pady=14)

    for label, val in [
        ("Título",   s["title"]),
        ("Artista",  s["artist"]),
        ("Álbum",    s["album"]),
        ("Duración", fmt(float(s["duration"]))),
        ("Archivo",  os.path.basename(str(s["path"]))),
        ("Ruta",     s["path"]),
    ]:
        row = tk.Frame(win, bg=T["BG_PANEL"])
        row.pack(fill="x", padx=20, pady=3)
        tk.Label(row, text=f"{label}:", width=10, font=F_SMALL,
                 bg=T["BG_PANEL"], fg=T["TEXT_MUTED"],
                 anchor="w").pack(side="left")
        tk.Label(row, text=str(val), font=F_SMALL,
                 bg=T["BG_PANEL"], fg=T["TEXT_MAIN"],
                 anchor="w", wraplength=270).pack(side="left")

# ══════════════════════════════════════════════════════════════
#                              AJUSTES
# ══════════════════════════════════════════════════════════════
def open_settings() -> None:
    win = tk.Toplevel(root)
    win.title("Ajustes")
    win.geometry("500x490")
    win.configure(bg=T["BG_PANEL"])
    win.grab_set()

    tk.Label(win, text="⚙  Ajustes",
             font=F_TITLE, bg=T["BG_PANEL"],
             fg=T["TEXT_MAIN"]).pack(pady=16)

                                                                        # Color de acento ─────────────────────────
    row1 = tk.Frame(win, bg=T["BG_PANEL"])
    row1.pack(fill="x", padx=24, pady=6)
    tk.Label(row1, text="Color de acento:",
             font=F_ARTIST, bg=T["BG_PANEL"],
             fg=T["TEXT_MAIN"]).pack(side="left")
    swatch = tk.Label(row1, bg=T["ACCENT"], width=4)
    swatch.pack(side="left", padx=10)

    def pick_accent() -> None:
        color = colorchooser.askcolor(
            color=T["ACCENT"], title="Color de acento"
        )[1]
        if color:
            T["ACCENT"] = color
            swatch.config(bg=color)
            btn_play.config(bg=color)
            btn_import.config(bg=color)
            lbl_logo.config(fg=color)

    tk.Button(row1, text="Cambiar", font=F_SMALL,
              bg=T["BG_CARD"], fg=T["TEXT_MAIN"],
              bd=0, relief="flat", padx=8, pady=4,
              cursor="hand2", command=pick_accent).pack(side="left")

                                                                            # Tema ────────────────────────────────────
    row2 = tk.Frame(win, bg=T["BG_PANEL"])
    row2.pack(fill="x", padx=24, pady=6)
    tk.Label(row2, text="Tema:", font=F_ARTIST,
             bg=T["BG_PANEL"], fg=T["TEXT_MAIN"]).pack(side="left")

    def _apply_theme(updates: dict[str, str]) -> None:
        T.update(updates)
        root.configure(bg=T["BG_DARK"])

    themes: list[tuple[str, dict[str, str]]] = [
        ("Oscuro", {
            "BG_DARK": "#0D0D0D", "BG_PANEL": "#141414",
            "BG_CARD": "#1A1A1A", "TEXT_MAIN": "#FFFFFF",
            "TEXT_SUB": "#A0A0A0", "TEXT_MUTED": "#535353",
        }),
        ("Claro", {
            "BG_DARK": "#F5F5F5", "BG_PANEL": "#E8E8E8",
            "BG_CARD": "#DCDCDC", "TEXT_MAIN": "#111111",
            "TEXT_SUB": "#555555", "TEXT_MUTED": "#888888",
        }),
        ("Midnight", {
            "BG_DARK": "#090916", "BG_PANEL": "#10102A",
            "BG_CARD": "#16163A", "TEXT_MAIN": "#E8E8FF",
            "TEXT_SUB": "#8888BB", "TEXT_MUTED": "#444466",
        }),
    ]
    for lbl_txt, updates in themes:
        tk.Button(
            row2, text=lbl_txt, font=F_SMALL,
            bg=T["BG_CARD"], fg=T["TEXT_MAIN"],
            bd=0, relief="flat", padx=12, pady=4,
            cursor="hand2",
            command=lambda u=updates: _apply_theme(u),
        ).pack(side="left", padx=4)

    # Carpeta de música ───────────────────────
    row3 = tk.Frame(win, bg=T["BG_PANEL"])
    row3.pack(fill="x", padx=24, pady=6)
    tk.Label(row3, text="Carpeta:", font=F_ARTIST,
             bg=T["BG_PANEL"], fg=T["TEXT_MAIN"]).pack(side="left")
    folder_var = tk.StringVar(value="No seleccionada")
    tk.Label(row3, textvariable=folder_var, font=F_SMALL,
             bg=T["BG_PANEL"], fg=T["TEXT_SUB"]).pack(side="left", padx=6)

    def pick_folder_settings() -> None:
        f = filedialog.askdirectory()
        if f:
            folder_var.set(os.path.basename(f))

    tk.Button(row3, text="Examinar", font=F_SMALL,
              bg=T["BG_CARD"], fg=T["TEXT_MAIN"],
              bd=0, relief="flat", padx=8, pady=4,
              cursor="hand2",
              command=pick_folder_settings).pack(side="left")

                                                                            # Atajos ──────────────────────────────────
    tk.Label(win, text="Atajos de teclado", font=F_NAV,
             bg=T["BG_PANEL"],
             fg=T["TEXT_MAIN"]).pack(anchor="w", padx=24, pady=(14, 4))
    shortcuts = (
        "  Espacio  →  Play / Pausa\n"
        "  →        →  Siguiente canción\n"
        "  ←        →  Canción anterior\n"
        "  ↑ / ↓    →  Subir / Bajar volumen\n"
        "  M        →  Silenciar\n"
        "  Supr     →  Eliminar canción seleccionada"
    )
    tk.Label(win, text=shortcuts, font=F_SMALL,
             bg=T["BG_PANEL"], fg=T["TEXT_SUB"],
             justify="left").pack(anchor="w", padx=32)

    tk.Button(win, text="Cerrar", font=F_NAV,
              bg=T["ACCENT"], fg="#000",
              bd=0, relief="flat", padx=20, pady=6,
              cursor="hand2", command=win.destroy).pack(pady=16)

# ══════════════════════════════════════════════════════════════
#                          IMPORTAR SPOTIFY
# ══════════════════════════════════════════════════════════════
def import_spotify() -> None:
    win = tk.Toplevel(root)
    win.title("Importar desde Spotify")
    win.geometry("480x330")
    win.configure(bg=T["BG_PANEL"])
    tk.Label(win, text="↓  Importar de Spotify",
             font=F_TITLE, bg=T["BG_PANEL"],
             fg=T["TEXT_MAIN"]).pack(pady=16)
    info = (
        "Para importar tu música de Spotify:\n\n"
        "1. Instala spotDL:\n"
        "     pip install spotdl\n\n"
        "2. Descarga una playlist en terminal:\n"
        "     spotdl sync 'URL_de_tu_playlist'\n\n"
        "3. Importa la carpeta descargada con\n"
        "   '📁 Importar carpeta' en el sidebar.\n\n"
        "También puedes usar spotipy (pip install spotipy)\n"
        "para leer metadata vía API de Spotify."
    )
    tk.Label(win, text=info, font=F_ARTIST,
             bg=T["BG_PANEL"], fg=T["TEXT_SUB"],
             justify="left").pack(padx=24, anchor="w")
    tk.Button(win, text="Entendido", font=F_NAV,
              bg=T["ACCENT"], fg="#000",
              bd=0, relief="flat", padx=20, pady=6,
              cursor="hand2", command=win.destroy).pack(pady=14)

# ══════════════════════════════════════════════════════════════
#                          REFRESCO DE LISTBOX
# ══════════════════════════════════════════════════════════════
def _refresh_list(select: int | None = None) -> None:
    listbox.delete(0, tk.END)
    indices = S.view_indices if S.view_indices is not None \
              else list(range(len(S.songs)))
    for pos, ri in enumerate(indices):
        s = S.songs[ri]
        heart = "❤ " if s.get("liked") else ""
        dur   = fmt(float(s["duration"]))
        listbox.insert(
            tk.END,
            f"  {ri+1:>3}.  {heart}{s['title']}"
            f"   —   {s['artist']}   [{dur}]",
        )
        if ri == S.current_index:
            listbox.itemconfig(pos, fg=T["ACCENT"])
    if select is not None and select in indices:
        pos = indices.index(select)
        listbox.selection_clear(0, tk.END)
        listbox.selection_set(pos)
        listbox.see(pos)

def _on_dbl_click(event: tk.Event) -> None:  # type: ignore[type-arg]
    sel = listbox.curselection()
    if not sel:
        return
    real_idx = S.view_indices[sel[0]] if S.view_indices else sel[0]
    load_and_play(real_idx)

# ══════════════════════════════════════════════════════════════
#                          H PROGRESO
# ══════════════════════════════════════════════════════════════
def _ticker() -> None:
    while True:
        if S.is_playing and S.song_length > 0:
            elapsed = S.play_offset + (time.monotonic() - S.play_start)
            if elapsed >= S.song_length:
                S.is_playing = False
                root.after(0, _song_ended)
            else:
                frac = min(elapsed / S.song_length, 1.0) * 100
                root.after(0, v_prog.set, frac)
                root.after(0, v_cur.set,  fmt(elapsed))
        time.sleep(0.4)

def _song_ended() -> None:
    btn_play.config(text="▶")
    pool = S.view_indices or list(range(len(S.songs)))
    pos  = pool.index(S.current_index) if S.current_index in pool else -1
    match S.repeat_mode:
        case "one":
            load_and_play(S.current_index)
        case "all":
            next_track()
        case _:
            if S.is_shuffled:
                next_track()
            elif 0 <= pos < len(pool) - 1:
                next_track()

threading.Thread(target=_ticker, daemon=True).start()

# ══════════════════════════════════════════════════════════════
#      VARIABLES Tk  (deben existir antes de construir widgets)
# ══════════════════════════════════════════════════════════════
root = tk.Tk()
root.title("LocalTune")
root.geometry("1280x820")
root.minsize(960, 660)
root.configure(bg=T["BG_DARK"])

v_title  = tk.StringVar(value="Sin canción seleccionada")
v_artist = tk.StringVar(value="—")
v_cur    = tk.StringVar(value="0:00")
v_total  = tk.StringVar(value="0:00")
v_vol    = tk.DoubleVar(value=70)
v_prog   = tk.DoubleVar(value=0)
v_search = tk.StringVar()
v_search.trace_add("write", apply_filter)

# ══════════════════════════════════════════════════════════════
#                              LAYOUT
# ══════════════════════════════════════════════════════════════
main_frame = tk.Frame(root, bg=T["BG_DARK"])
main_frame.pack(fill="both", expand=True, side="top")

                                                                    # ─────────────────────  SIDEBAR  ─────────────────────────────
sidebar = tk.Frame(main_frame, bg=T["BG_PANEL"], width=228)
sidebar.pack(side="left", fill="y")
sidebar.pack_propagate(False)

lbl_logo = tk.Label(sidebar, text="🎵 LocalTune",
                     font=("Helvetica", 16, "bold"),
                     bg=T["BG_PANEL"], fg=T["ACCENT"], pady=20)
lbl_logo.pack(fill="x", padx=16)

tk.Frame(sidebar, bg=T["BG_HOVER"], height=1).pack(fill="x", padx=16, pady=4)

for nav_txt, nav_cmd in [
    ("🏠  Inicio",         show_library),
    ("🔍  Buscar",         lambda: search_entry.focus()),
    ("📚  Tu Biblioteca",  show_library),
    ("❤  Favoritos",      show_favorites),
]:
    tk.Button(
        sidebar, text=nav_txt, font=F_NAV,
        bg=T["BG_PANEL"], fg=T["TEXT_MAIN"],
        bd=0, relief="flat",
        activebackground=T["BG_HOVER"],
        activeforeground=T["ACCENT"],
        anchor="w", padx=16, pady=9,
        cursor="hand2", command=nav_cmd,
    ).pack(fill="x")

tk.Frame(sidebar, bg=T["BG_HOVER"], height=1).pack(fill="x", padx=16, pady=8)
tk.Label(sidebar, text="PLAYLISTS", font=F_SMALL,
         bg=T["BG_PANEL"], fg=T["TEXT_MUTED"],
         anchor="w", padx=16).pack(fill="x", pady=(4, 0))

# zona scrollable playlists
pl_canvas = tk.Canvas(sidebar, bg=T["BG_PANEL"],
                       bd=0, highlightthickness=0, height=160)
pl_canvas.pack(fill="x")
frame_playlists = tk.Frame(pl_canvas, bg=T["BG_PANEL"])
pl_canvas.create_window((0, 0), window=frame_playlists, anchor="nw")
frame_playlists.bind(
    "<Configure>",
    lambda e: pl_canvas.configure(
        scrollregion=pl_canvas.bbox("all")
    ),
)

tk.Button(sidebar, text="＋  Nueva playlist", font=F_ARTIST,
          bg=T["BG_PANEL"], fg=T["ACCENT"],
          bd=0, relief="flat",
          activebackground=T["BG_HOVER"],
          anchor="w", padx=16, pady=6,
          cursor="hand2", command=new_playlist).pack(fill="x", pady=(4, 0))

tk.Frame(sidebar, bg=T["BG_HOVER"], height=1).pack(fill="x", padx=16, pady=6)

for sb_txt, sb_cmd in [
    ("↓  Importar de Spotify", import_spotify),
    ("📁  Importar carpeta",    import_folder),
    ("⚙  Ajustes",             open_settings),
]:
    tk.Button(
        sidebar, text=sb_txt, font=F_SMALL,
        bg=T["BG_PANEL"], fg=T["TEXT_MUTED"],
        bd=0, relief="flat",
        activebackground=T["BG_HOVER"],
        activeforeground=T["TEXT_MAIN"],
        anchor="w", padx=16, pady=6,
        cursor="hand2", command=sb_cmd,
    ).pack(fill="x")

                                                                                # ─────────────────────  CONTENIDO  ───────────────────────────
content = tk.Frame(main_frame, bg=T["BG_DARK"])
content.pack(side="left", fill="both", expand=True)

hdr = tk.Frame(content, bg=T["BG_DARK"], pady=16)
hdr.pack(fill="x", padx=24)

lbl_section = tk.Label(hdr, text="Tu Biblioteca",
                        font=F_TITLE, bg=T["BG_DARK"],
                        fg=T["TEXT_MAIN"])
lbl_section.pack(side="left")

btn_import = tk.Button(
    hdr, text="+ Importar archivos",
    font=F_SMALL, bg=T["ACCENT"], fg="#000",
    bd=0, relief="flat", padx=12, pady=6,
    activebackground=T["ACCENT2"],
    cursor="hand2", command=import_files,
)
btn_import.pack(side="right")

tk.Button(hdr, text="🗑 Eliminar", font=F_SMALL,
          bg=T["BG_CARD"], fg=T["TEXT_SUB"],
          bd=0, relief="flat", padx=10, pady=6,
          activebackground=T["BG_HOVER"],
          cursor="hand2",
          command=remove_selected).pack(side="right", padx=8)

tk.Button(hdr, text="➕ Playlist", font=F_SMALL,
          bg=T["BG_CARD"], fg=T["TEXT_SUB"],
          bd=0, relief="flat", padx=10, pady=6,
          activebackground=T["BG_HOVER"],
          cursor="hand2",
          command=add_to_playlist).pack(side="right", padx=4)

# Búsqueda
sf = tk.Frame(content, bg=T["BG_DARK"], padx=24, pady=4)
sf.pack(fill="x")
search_entry = tk.Entry(
    sf, textvariable=v_search, font=F_ARTIST,
    bg=T["BG_CARD"], fg=T["TEXT_MAIN"],
    insertbackground=T["TEXT_MAIN"],
    bd=0, relief="flat",
    highlightthickness=1,
    highlightbackground=T["BG_HOVER"],
    highlightcolor=T["ACCENT"],
)
search_entry.pack(fill="x", ipady=8)

def _sfocus(e: tk.Event | None = None) -> None:                      # type: ignore[type-arg]
    if search_entry.get() == _SEARCH_PH:
        search_entry.delete(0, tk.END)
        search_entry.config(fg=T["TEXT_MAIN"])

def _sblur(e: tk.Event | None = None) -> None:                           # type: ignore[type-arg]
    if not v_search.get():
        search_entry.insert(0, _SEARCH_PH)
        search_entry.config(fg=T["TEXT_MUTED"])

search_entry.bind("<FocusIn>",  _sfocus)
search_entry.bind("<FocusOut>", _sblur)
_sblur()

# Cabecera columnas
ch = tk.Frame(content, bg=T["BG_DARK"], padx=24)
ch.pack(fill="x", pady=(10, 4))
tk.Label(ch, text="#    Título — Artista", font=F_SMALL,
         bg=T["BG_DARK"], fg=T["TEXT_MUTED"],
         anchor="w").pack(side="left")
tk.Label(ch, text="Dur.", font=F_SMALL,
         bg=T["BG_DARK"], fg=T["TEXT_MUTED"],
         anchor="e").pack(side="right")
tk.Frame(content, bg=T["BG_HOVER"], height=1).pack(fill="x", padx=24, pady=2)

# Listbox
lf = tk.Frame(content, bg=T["BG_DARK"], padx=24)
lf.pack(fill="both", expand=True)
scr = tk.Scrollbar(lf, bg=T["BG_DARK"],
                    troughcolor=T["BG_DARK"],
                    activebackground=T["ACCENT"], bd=0)
scr.pack(side="right", fill="y")
listbox = tk.Listbox(
    lf,
    bg=T["BG_DARK"], fg=T["TEXT_MAIN"],
    selectbackground=T["BG_HOVER"],
    selectforeground=T["ACCENT"],
    font=F_ARTIST, bd=0, relief="flat",
    highlightthickness=0, activestyle="none",
    yscrollcommand=scr.set,
)
listbox.pack(fill="both", expand=True)
scr.config(command=listbox.yview)
listbox.bind("<Double-Button-1>", _on_dbl_click)

                                                                    # ─────────────────────  NOW PLAYING  ─────────────────────────
np_panel = tk.Frame(main_frame, bg=T["BG_PANEL"], width=265)
np_panel.pack(side="right", fill="y")
np_panel.pack_propagate(False)

tk.Label(np_panel, text="REPRODUCIENDO AHORA",
         font=F_SMALL, bg=T["BG_PANEL"],
         fg=T["TEXT_MUTED"]).pack(pady=(18, 10))

cover_holder = tk.Frame(np_panel, bg=T["BG_CARD"],
                         width=220, height=220)
cover_holder.pack()
cover_holder.pack_propagate(False)

_def_cover = default_cover()
cover_lbl   = tk.Label(cover_holder, image=_def_cover,
                        bg=T["BG_CARD"])
cover_lbl.image = _def_cover                                                       # type: ignore[attr-defined]
cover_lbl.place(relx=0.5, rely=0.5, anchor="center")

tk.Button(np_panel, text="📷  Cambiar portada",
          font=F_SMALL, bg=T["BG_CARD"], fg=T["TEXT_SUB"],
          bd=0, relief="flat",
          activebackground=T["BG_HOVER"],
          cursor="hand2", pady=6,
          command=set_cover_for_song).pack(fill="x", padx=20, pady=8)

tk.Label(np_panel, textvariable=v_title,
         font=F_SONG, bg=T["BG_PANEL"],
         fg=T["TEXT_MAIN"], wraplength=220).pack(pady=(6, 2))
tk.Label(np_panel, textvariable=v_artist,
         font=F_ARTIST, bg=T["BG_PANEL"],
         fg=T["TEXT_SUB"]).pack()

ar = tk.Frame(np_panel, bg=T["BG_PANEL"])
ar.pack(pady=10)

btn_like = tk.Button(ar, text="♡",
                      font=("Helvetica", 16),
                      bg=T["BG_PANEL"], fg=T["TEXT_MUTED"],
                      bd=0, relief="flat",
                      activebackground=T["BG_HOVER"],
                      cursor="hand2", padx=10,
                      command=toggle_like)
btn_like.pack(side="left")

tk.Button(ar, text="⋯", font=("Helvetica", 16),
          bg=T["BG_PANEL"], fg=T["TEXT_MUTED"],
          bd=0, relief="flat",
          activebackground=T["BG_HOVER"],
          cursor="hand2", padx=10,
          command=song_info).pack(side="left")

tk.Button(ar, text="➕", font=("Helvetica", 16),
          bg=T["BG_PANEL"], fg=T["TEXT_MUTED"],
          bd=0, relief="flat",
          activebackground=T["BG_HOVER"],
          cursor="hand2", padx=10,
          command=add_to_playlist).pack(side="left")

                                                        # ─────────────────────  PLAYER BAR  ──────────────────────────
player_bar = tk.Frame(root, bg=T["BG_PANEL"], height=95)
player_bar.pack(side="bottom", fill="x")
player_bar.pack_propagate(False)
tk.Frame(player_bar, bg=T["BG_HOVER"], height=1).pack(fill="x")

bar_inner = tk.Frame(player_bar, bg=T["BG_PANEL"])
bar_inner.pack(fill="both", expand=True, padx=24, pady=6)

                                                                # Izquierda: info canción
li = tk.Frame(bar_inner, bg=T["BG_PANEL"], width=280)
li.pack(side="left", fill="y")
li.pack_propagate(False)
tk.Label(li, textvariable=v_title, font=F_SONG,
         bg=T["BG_PANEL"], fg=T["TEXT_MAIN"],
         anchor="w").pack(fill="x")
tk.Label(li, textvariable=v_artist, font=F_SMALL,
         bg=T["BG_PANEL"], fg=T["TEXT_SUB"],
         anchor="w").pack(fill="x")

                                                                # Centro: controles + progreso
ctr = tk.Frame(bar_inner, bg=T["BG_PANEL"])
ctr.pack(side="left", fill="both", expand=True, padx=16)

ctrl = tk.Frame(ctr, bg=T["BG_PANEL"])
ctrl.pack(pady=(2, 0))

btn_shuf = tk.Button(ctrl, text="⇄", font=F_BTN,
                      bg=T["BG_PANEL"], fg=T["TEXT_MUTED"],
                      bd=0, relief="flat",
                      activebackground=T["BG_PANEL"],
                      cursor="hand2",
                      command=toggle_shuffle)
btn_shuf.pack(side="left", padx=6)

tk.Button(ctrl, text="⏮", font=F_BTN,
          bg=T["BG_PANEL"], fg=T["TEXT_MAIN"],
          bd=0, relief="flat",
          activebackground=T["BG_PANEL"],
          cursor="hand2",
          command=prev_track).pack(side="left", padx=6)

btn_play = tk.Button(ctrl, text="▶",
                      font=("Helvetica", 24, "bold"),
                      bg=T["ACCENT"], fg="#000",
                      bd=0, relief="flat", width=3,
                      activebackground=T["ACCENT2"],
                      cursor="hand2",
                      command=play_pause)
btn_play.pack(side="left", padx=8)

tk.Button(ctrl, text="⏭", font=F_BTN,
          bg=T["BG_PANEL"], fg=T["TEXT_MAIN"],
          bd=0, relief="flat",
          activebackground=T["BG_PANEL"],
          cursor="hand2",
          command=next_track).pack(side="left", padx=6)

btn_rep = tk.Button(ctrl, text="🔁", font=F_BTN,
                     bg=T["BG_PANEL"], fg=T["TEXT_MUTED"],
                     bd=0, relief="flat",
                     activebackground=T["BG_PANEL"],
                     cursor="hand2",
                     command=toggle_repeat)
btn_rep.pack(side="left", padx=6)

                                                                    # Barra de progreso
pr = tk.Frame(ctr, bg=T["BG_PANEL"])
pr.pack(fill="x", pady=(2, 0))

tk.Label(pr, textvariable=v_cur, font=F_SMALL,
         bg=T["BG_PANEL"], fg=T["TEXT_MUTED"]).pack(side="left")

_sty = ttk.Style()
_sty.theme_use("default")
_sty.configure("P.Horizontal.TScale",
                background=T["BG_PANEL"],
                troughcolor=T["SLIDER_BG"],
                sliderthickness=12,
                sliderrelief="flat")

prog_slider = ttk.Scale(
    pr, from_=0, to=100, variable=v_prog,
    orient="horizontal",
    style="P.Horizontal.TScale",
    command=lambda v: None,                                  # actualiza variable; seek en release
)
prog_slider.pack(side="left", fill="x", expand=True, padx=8)
prog_slider.bind("<ButtonRelease-1>",
                 lambda e: seek_to(v_prog.get()))

tk.Label(pr, textvariable=v_total, font=F_SMALL,
         bg=T["BG_PANEL"], fg=T["TEXT_MUTED"]).pack(side="right")

                                                                        # Derecha: volumen + extras
ri_f = tk.Frame(bar_inner, bg=T["BG_PANEL"], width=215)
ri_f.pack(side="right", fill="y")
ri_f.pack_propagate(False)

extras = tk.Frame(ri_f, bg=T["BG_PANEL"])
extras.pack(anchor="e", pady=(8, 2))
for ex_icon, ex_cmd in [("📋", open_queue), ("🎛", open_equalizer)]:
    tk.Button(extras, text=ex_icon, font=F_ARTIST,
              bg=T["BG_PANEL"], fg=T["TEXT_MUTED"],
              bd=0, relief="flat",
              activebackground=T["BG_HOVER"],
              cursor="hand2", padx=6,
              command=ex_cmd).pack(side="left")

vr = tk.Frame(ri_f, bg=T["BG_PANEL"])
vr.pack(anchor="e")

lbl_vol_icon = tk.Label(vr, text="🔊", font=F_ARTIST,
                         bg=T["BG_PANEL"], fg=T["TEXT_MUTED"],
                         cursor="hand2")
lbl_vol_icon.pack(side="left")
lbl_vol_icon.bind("<Button-1>", toggle_mute)

vol_slider = ttk.Scale(
    vr, from_=0, to=100, variable=v_vol,
    orient="horizontal",
    style="P.Horizontal.TScale",
    length=120,
    command=lambda v: set_volume(float(v)),
)
vol_slider.pack(side="left", padx=4)

# ══════════════════════════════════════════════════════════════
#                          ATAJOS DE TECLADO
# ══════════════════════════════════════════════════════════════
def _kb_volup(e: tk.Event) -> None:                                            # type: ignore[type-arg]
    new = min(100.0, v_vol.get() + 5)
    v_vol.set(new); set_volume(new)

def _kb_voldown(e: tk.Event) -> None:                                          # type: ignore[type-arg]
    new = max(0.0, v_vol.get() - 5)
    v_vol.set(new); set_volume(new)

root.bind("<space>",
          lambda e: play_pause()
          if root.focus_get() is not search_entry else None)
root.bind("<Right>",  lambda e: next_track())
root.bind("<Left>",   lambda e: prev_track())
root.bind("<Up>",     _kb_volup)
root.bind("<Down>",   _kb_voldown)
root.bind("m",        toggle_mute)
root.bind("<Delete>", lambda e: remove_selected())

# ══════════════════════════════════════════════════════════════
#                              ARRANQUE
# ══════════════════════════════════════════════════════════════
load_data()
for pl_name in S.playlists:
    _add_playlist_btn(pl_name)
S.view_indices = list(range(len(S.songs)))
_refresh_list()
pygame.mixer.music.set_volume(S.volume)
v_vol.set(S.volume * 100)

root.mainloop()
save_data()
