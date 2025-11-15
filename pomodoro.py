import time
import tkinter as tk
from tkinter import messagebox
import ttkbootstrap as ttk
from ttkbootstrap import Style
from PIL import Image, ImageTk, ImageFilter, ImageOps
import vlc
import os
import math

# ========================
# Paramètres Pomodoro (s)
# ========================
WORK_TIME = 25 * 60
SHORT_BREAK_TIME = 5 * 60
LONG_BREAK_TIME = 15 * 60

# ========================
# Fichiers
# ========================
LOFI_PATH = "lofi.mp3"
BELL_PATH = "clochette.mp3"
BG_IMAGE = "IMG.jpg"  # image de fond

# ========================
# UI sympa + fluide
# ========================
class PomodoroTimer:
    def __init__(self):
        # --- Fenêtre ---
        self.root = tk.Tk()
        self.root.title("Pomodoro • Focus")
        self.root.minsize(520, 420)

        # Thème modernisé
        self.style = Style(theme="minty")  # "cyborg" si tu veux dark
        self.root.configure(bg=self.style.colors.bg)

        # --- Variables internes ---
        self.phase = "work"  # "work" ou "break"
        self.pomodoros_completed = 0
        self.is_running = False
        self.start_ts = None
        self.target_ts = None
        self.duration = WORK_TIME

        # --- Audio (VLC) ---
        try:
            self.vlc_instance = vlc.Instance("--no-video")
        except Exception as e:
            messagebox.showerror("VLC manquant", f"LibVLC introuvable.\n{e}")
            raise
        self.lofi_player = None
        self.bell_player = None

        # --- Fond d’écran réactif ---
        self.bg_original = None
        self.bg_photo = None
        self.bg_label = tk.Label(self.root, bd=0)
        self.bg_label.place(x=0, y=0, relwidth=1, relheight=1)

        self.resize_job = None
        self.last_bg_size = (0, 0)
        self._load_background()

        # --- Container central (carte) ---
        self.card = ttk.Frame(self.root, padding=20, bootstyle="light")
        self.card.place(relx=0.5, rely=0.5, anchor="center")
        self.card.bind("<Configure>", self._center_card)

        # Shadow cheap: un cadre dessous
        self.shadow = tk.Frame(self.root, bg="#00000020")
        self.shadow.place(x=-1000, y=-1000)  # sera placé au centre ensuite

        # --- Titre ---
        self.title_label = ttk.Label(
            self.card,
            text="Session de travail",
            anchor="center",
            font=("Segoe UI", 14, "bold"),
        )
        self.title_label.pack(pady=(0, 10))

        # --- Canvas progress ring ---
        self.canvas_size = 260
        self.canvas = tk.Canvas(self.card, width=self.canvas_size, height=self.canvas_size,
                                highlightthickness=0, bg="")
        self.canvas.pack(pady=5)

        # --- Compteur ---
        self.timer_label = ttk.Label(
            self.card,
            text="25:00",
            anchor="center",
            font=("Segoe UI", 36, "bold"),
        )
        self.timer_label.pack(pady=(8, 16))

        # --- Boutons ---
        btns = ttk.Frame(self.card)
        btns.pack()

        self.start_button = ttk.Button(btns, text="Start", command=self.start_timer, bootstyle="success-outline")
        self.start_button.grid(row=0, column=0, padx=6)

        self.stop_button = ttk.Button(btns, text="Stop", command=self.stop_timer, state=tk.DISABLED, bootstyle="danger")
        self.stop_button.grid(row=0, column=1, padx=6)

        self.skip_button = ttk.Button(btns, text="Skip", command=self.skip_phase, state=tk.DISABLED, bootstyle="secondary-outline")
        self.skip_button.grid(row=0, column=2, padx=6)

        # --- Responsive: redimension fluide ---
        self.root.bind("<Configure>", self._on_root_resize)
        self._layout_card()

        # Affichage initial
        self._update_display(remaining=self.duration)
        self._draw_ring(progress=0.0)

        self.root.mainloop()

    # ==============
    # Audio (VLC)
    # ==============
    def play_lofi(self, volume=22):
        try:
            if self.lofi_player is None:
                self.lofi_player = self.vlc_instance.media_player_new()
                media = self.vlc_instance.media_new(LOFI_PATH)
                media.add_option("input-repeat=-1")  # boucle infinie
                self.lofi_player.set_media(media)
                self.lofi_player.audio_set_volume(volume)  # 0..100
            if not self.lofi_player.is_playing():
                self.lofi_player.play()
        except Exception as e:
            print(f"⚠️ Lofi non joué: {e}")

    def stop_lofi(self):
        try:
            if self.lofi_player is not None:
                self.lofi_player.stop()
        except Exception as e:
            print(f"⚠️ Lofi non stoppé: {e}")

    def ring_bell(self, volume=85):
        try:
            bell = self.vlc_instance.media_player_new()
            media = self.vlc_instance.media_new(BELL_PATH)
            bell.set_media(media)
            bell.audio_set_volume(volume)
            bell.play()
            # garder une référence courte pour éviter GC immédiat
            self.bell_player = bell
            self.root.after(4000, self._cleanup_bell)
        except Exception as e:
            print(f"⚠️ Clochette non jouée: {e}")

    def _cleanup_bell(self):
        try:
            if self.bell_player and not self.bell_player.is_playing():
                self.bell_player.stop()
            self.bell_player = None
        except:
            pass

    # ===================
    # Background fluide
    # ===================
    def _load_background(self):
        try:
            img = Image.open(BG_IMAGE).convert("RGB")
            # léger flou + vignette douce pour lisibilité
            img = img.filter(ImageFilter.GaussianBlur(radius=1.2))
            self.bg_original = img
            self._resize_background(sharp=True)
        except Exception as e:
            print(f"⚠️ Impossible de charger le fond d’écran : {e}")
            self.root.configure(bg="#1a1f2b")

    def _on_root_resize(self, event):
        if event.widget is not self.root:
            return
        # Debounce pour éviter de recalculer 60 fois/s
        if self.resize_job:
            self.root.after_cancel(self.resize_job)
        # Preview rapide pendant le drag pour fluidité, puis sharp
        self._resize_background(sharp=False)
        self.resize_job = self.root.after(120, lambda: self._resize_background(sharp=True))
        self._layout_card()

    def _resize_background(self, sharp=True):
        if not self.bg_original:
            return
        w = max(1, self.root.winfo_width())
        h = max(1, self.root.winfo_height())

        if (w, h) == self.last_bg_size and sharp:
            return

        # cover: on garde le ratio, on remplit tout, on crop si besoin
        bg = self.bg_original.copy()
        bg = ImageOps.fit(bg, (w, h), method=Image.Resampling.LANCZOS, bleed=0.0, centering=(0.5, 0.5))
        if not sharp:
            # version plus légère pour le drag: downscale puis upscale (cheap)
            bg_small = bg.resize((w//2 or 1, h//2 or 1), Image.Resampling.BILINEAR)
            bg = bg_small.resize((w, h), Image.Resampling.BILINEAR)

        # léger assombrissement pour lisibilité du texte
        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 60))
        bg = bg.convert("RGBA")
        bg.alpha_composite(overlay)

        self.bg_photo = ImageTk.PhotoImage(bg)
        self.bg_label.configure(image=self.bg_photo)
        self.bg_label.image = self.bg_photo
        self.last_bg_size = (w, h)

    # ===================
    # Mise en page carte
    # ===================
    def _layout_card(self):
        # taille relative de la carte
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        cw = min(520, int(w * 0.8))
        ch = min(420, int(h * 0.8))
        self.card.place_configure(width=cw, height=ch)
        # ombre sous la carte
        self.shadow.place_configure(width=cw, height=ch)
        self._center_card()

    def _center_card(self, event=None):
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        # position carte
        self.card.place_configure(x=(w - self.card.winfo_width()) // 2,
                                  y=(h - self.card.winfo_height()) // 2)
        # shadow un peu décalée
        self.shadow.place_configure(x=(w - self.card.winfo_width()) // 2 + 6,
                                    y=(h - self.card.winfo_height()) // 2 + 8)

    # ===================
    # Logique Pomodoro
    # ===================
    def start_timer(self):
        if self.is_running:
            return
        self.is_running = True
        self.start_button.configure(state=tk.DISABLED)
        self.stop_button.configure(state=tk.NORMAL)
        self.skip_button.configure(state=tk.NORMAL)

        # horloge précise
        now = time.monotonic()
        self.start_ts = now
        self.target_ts = now + self.duration

        if self.phase == "work":
            self.title_label.configure(text="Session de travail")
            self.play_lofi()
        else:
            self.title_label.configure(text="Pause")
            self.stop_lofi()

        self._tick()

    def stop_timer(self):
        if not self.is_running:
            return
        self.is_running = False
        self.start_button.configure(state=tk.NORMAL)
        self.stop_button.configure(state=tk.DISABLED)
        self.skip_button.configure(state=tk.DISABLED)
        self.stop_lofi()

    def skip_phase(self):
        # termine immédiatement la phase
        if not self.is_running:
            return
        self.target_ts = time.monotonic()  # force fin

    def _end_work(self):
        self.stop_lofi()
        self.ring_bell()
        self.pomodoros_completed += 1
        long_break = (self.pomodoros_completed % 4 == 0)
        self.phase = "break"
        self.duration = LONG_BREAK_TIME if long_break else SHORT_BREAK_TIME
        self.title_label.configure(text="Pause")
        messagebox.showinfo(
            "Pause",
            "Longue pause, respire 15 min." if long_break else "Petite pause 5 min, bouge un peu."
        )
        self._restart_phase()

    def _end_break(self):
        self.ring_bell()
        self.phase = "work"
        self.duration = WORK_TIME
        self.title_label.configure(text="Session de travail")
        messagebox.showinfo("Travail", "C’est reparti pour 25 min.")
        self._restart_phase()

    def _restart_phase(self):
        # relance chronomètre
        now = time.monotonic()
        self.start_ts = now
        self.target_ts = now + self.duration
        if self.phase == "work":
            self.play_lofi()
        else:
            self.stop_lofi()

    def _tick(self):
        if not self.is_running:
            return

        now = time.monotonic()
        remaining = max(0.0, self.target_ts - now)
        self._update_display(remaining)
        progress = 1.0 - (remaining / self.duration) if self.duration > 0 else 1.0
        self._draw_ring(progress)

        if remaining <= 0.0001:
            if self.phase == "work":
                self._end_work()
            else:
                self._end_break()

        # 10 FPS pour fluidité sans flinguer le CPU
        self.root.after(100, self._tick)

    # ===================
    # Affichage
    # ===================
    def _update_display(self, remaining: float):
        total_seconds = int(round(remaining))
        minutes, seconds = divmod(total_seconds, 60)
        self.timer_label.configure(text=f"{minutes:02d}:{seconds:02d}")

    def _draw_ring(self, progress: float):
        # Efface
        self.canvas.delete("all")

        # Dimensions
        size = self.canvas_size
        pad = 16
        x0, y0 = pad, pad
        x1, y1 = size - pad, size - pad
        cx = cy = size // 2
        r = (size - 2 * pad) // 2

        # Couleurs
        base = "#E6EAF2"
        if self.phase == "work":
            accent = "#2DB47C"  # vert menthe
        else:
            accent = "#5B8DEF"  # bleu calme

        # Cercle de fond
        self.canvas.create_oval(x0, y0, x1, y1, outline=base, width=14)

        # Arc de progression (départ en haut)
        start_angle = -90
        extent = progress * 360.0
        self.canvas.create_arc(x0, y0, x1, y1, start=start_angle, extent=extent,
                               style="arc", outline=accent, width=14, capstyle=tk.ROUND)

        # Petit indicateur de pointe
        angle_rad = math.radians(start_angle + extent)
        px = cx + r * math.cos(angle_rad)
        py = cy + r * math.sin(angle_rad)
        self.canvas.create_oval(px-5, py-5, px+5, py+5, fill=accent, outline="")

# ========================
# Lancement
# ========================
if __name__ == "__main__":
    PomodoroTimer()
