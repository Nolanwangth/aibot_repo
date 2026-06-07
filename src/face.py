"""Animated cartoon eyes — fullscreen tkinter, switches between emotional states."""
import tkinter as tk
import random

BG = "#0a0a14"
EYE_WHITE = "#f0f0f0"
PUPIL = "#1a1a2e"


class Face:
    def __init__(self):
        self.state = "idle"
        self._blink = 0
        self._blink_wait = 0

    def setup(self):
        """Initialize tkinter window. Call on main thread before run()."""
        self._root = tk.Tk()
        self._root.title("小灵")
        self._root.configure(bg=BG)
        self._root.attributes("-fullscreen", True)
        self._c = tk.Canvas(self._root, bg=BG, highlightthickness=0)
        self._c.pack(fill="both", expand=True)

    def set_state(self, state: str):
        self.state = state

    def run(self):
        """Start animation loop and block on tkinter mainloop."""
        self._tick()
        self._root.mainloop()

    def _tick(self):
        # Natural blinking
        if self._blink > 0:
            self._blink += 0.15
            if self._blink >= 2.0:
                self._blink = 0
                self._blink_wait = random.randint(40, 100)
        elif self._blink_wait > 0:
            self._blink_wait -= 1
        elif random.random() < 0.01:
            self._blink = 0.01

        self._draw()
        self._c.after(30, self._tick)

    def _draw(self):
        self._c.delete("all")
        w, h = self._c.winfo_width(), self._c.winfo_height()
        if w < 200 or h < 200:
            return

        cx, cy = w // 2, h // 2
        gap = w * 0.22
        rx, ry = w * 0.11, h * 0.15

        for ex in (cx - gap, cx + gap):
            self._draw_eye(ex, cy, rx, ry)

    def _draw_eye(self, ex, ey, rx, ry):
        if self.state == "listening":
            hs, ps = 1.15, 1.2
        elif self.state == "thinking":
            hs, ps = 0.5, 0.85
        elif self.state == "happy":
            self._draw_happy_eye(ex, ey, rx, ry)
            return
        else:
            hs, ps = 1.0, 1.0

        if self._blink > 0:
            hs *= 0.05 if self._blink >= 1.0 else 1.0 - self._blink * 0.95

        cry = ry * hs
        self._c.create_oval(ex - rx, ey - cry, ex + rx, ey + cry,
                            fill=EYE_WHITE, outline="#666", width=2)
        prx, pry = rx * 0.4 * ps, cry * 0.55 * ps
        self._c.create_oval(ex - prx, ey - pry, ex + prx, ey + pry,
                            fill=PUPIL, outline="")
        hl = prx * 0.3
        self._c.create_oval(ex - prx * 0.5 - hl, ey - pry * 0.5 - hl,
                            ex - prx * 0.5 + hl, ey - pry * 0.5 + hl,
                            fill="#fff", outline="")

    def _draw_happy_eye(self, ex, ey, rx, ry):
        ary = ry * 0.5
        self._c.create_arc(ex - rx, ey - ary, ex + rx, ey + ary,
                           start=0, extent=180, style="chord",
                           fill="#ddd", outline="#888", width=2)
