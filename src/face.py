"""Animated vector-pixel expression mask.

Only renders neon eyebrow/eye/mouth pixels on a dark mask surface.
No head, helmet, body, or decorative shell.
"""

import math
import random
import tkinter as tk
from PIL import Image, ImageDraw, ImageFilter, ImageTk

from .moods import BLACK, MOODS, render_frame

PX = 12
GRID_W = 24
GRID_H = 20
SCR_W = GRID_W * PX
SCR_H = GRID_H * PX

FPS = 30
FRAME_MS = 1000 // FPS
FADE_FRAMES = 14

BG_COLOR = "#050609"
MASK_COLOR = (2, 3, 6, 225)
SCAN_ALPHA = 10


def _ease(t: float) -> float:
    return t * t * (3 - 2 * t)


def _grid_to_layer(grid: list, alpha_mul: float = 1.0) -> Image.Image:
    """Convert a 24x20 mood grid to a transparent RGBA pixel layer."""
    img = Image.new("RGBA", (SCR_W, SCR_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pad = max(1, PX // 7)
    radius = max(1, PX // 5)

    for y in range(GRID_H):
        for x in range(GRID_W):
            r, g, b, a = grid[y][x]
            if a <= 0 or (r, g, b) == BLACK:
                continue

            alpha = int(a * alpha_mul)
            x1 = x * PX + pad
            y1 = y * PX + pad
            x2 = (x + 1) * PX - pad
            y2 = (y + 1) * PX - pad
            draw.rounded_rectangle((x1, y1, x2, y2), radius=radius, fill=(r, g, b, alpha))

    return img


class Face:
    def __init__(self):
        self.state = "idle"
        self._mood = "calm"
        self._target_mood = "calm"

        self._fading = False
        self._fade_frame = 0
        self._from_grid = None
        self._to_mood = "calm"

        self._anim_t = 0.0
        self._float_offset = 0.0
        self._particles = []

        self._root = None
        self._c = None
        self._canvas_w = 800
        self._canvas_h = 600
        self._composite_tk = None

    def setup(self):
        self._root = tk.Tk()
        self._root.title("小灵")
        self._root.configure(bg=BG_COLOR)
        self._root.geometry("720x720")
        self._root.minsize(260, 220)
        self._root.resizable(True, True)

        self._c = tk.Canvas(self._root, bg=BG_COLOR, highlightthickness=0)
        self._c.pack(fill="both", expand=True)
        self._rebuild_canvas()

    def _rebuild_canvas(self):
        if not self._c:
            return
        self._c.update_idletasks()
        self._canvas_w = self._c.winfo_width() or 800
        self._canvas_h = self._c.winfo_height() or 600

    def set_state(self, state: str):
        self.state = state

    def set_mood(self, mood: str):
        if mood in MOODS and mood != self._mood:
            self._set_mood(mood)

    def _set_mood(self, mood: str):
        if not self._fading:
            self._from_grid = render_frame(self._mood, self._anim_t)
        self._to_mood = mood
        self._target_mood = mood
        self._fading = True
        self._fade_frame = 0

    def get_mood(self) -> str:
        return self._mood

    def run(self):
        self._tick()
        self._root.mainloop()

    def _tick(self):
        self._anim_t = (self._anim_t + 0.035) % 1000
        self._float_offset = math.sin(self._anim_t * 1.25) * 5
        self._update_particles()

        if self._fading:
            self._fade_frame += 1
            if self._fade_frame >= FADE_FRAMES:
                self._fading = False
                self._mood = self._to_mood

        self._draw()
        self._c.after(FRAME_MS, self._tick)

    def _update_particles(self):
        if random.random() < 0.05:
            self._particles.append({
                "x": random.randint(0, max(1, self._canvas_w)),
                "y": random.randint(0, max(1, self._canvas_h)),
                "life": 0,
                "max": random.randint(30, 90),
            })

        alive = []
        for p in self._particles:
            p["life"] += 1
            if p["life"] < p["max"]:
                alive.append(p)
        self._particles = alive

    def _expression_layer(self) -> Image.Image:
        if self._fading and self._from_grid:
            frac = _ease(self._fade_frame / FADE_FRAMES)
            from_layer = _grid_to_layer(self._from_grid, 1.0 - frac)
            to_grid = render_frame(self._to_mood, self._anim_t)
            to_layer = _grid_to_layer(to_grid, frac)
            return Image.alpha_composite(from_layer, to_layer)

        return _grid_to_layer(render_frame(self._mood, self._anim_t))

    def _render_mask(self) -> Image.Image:
        expression = self._expression_layer()
        mood = self._to_mood if self._fading else self._mood
        glow_color = MOODS.get(mood, MOODS["calm"]).get("glow", (0, 100, 180))

        glow = expression.filter(ImageFilter.GaussianBlur(radius=PX * 0.9))
        glow2 = expression.filter(ImageFilter.GaussianBlur(radius=PX * 0.35))

        mask = Image.new("RGBA", (SCR_W, SCR_H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(mask)

        face_pad_x = PX * 3
        face_pad_y = PX * 2
        face_box = (face_pad_x, face_pad_y, SCR_W - face_pad_x, SCR_H - face_pad_y)
        draw.rounded_rectangle(face_box, radius=PX * 3, fill=MASK_COLOR)

        for y in range(face_pad_y + PX, SCR_H - face_pad_y, PX):
            draw.line(
                (face_pad_x + PX, y, SCR_W - face_pad_x - PX, y),
                fill=(35, 45, 55, SCAN_ALPHA),
                width=1,
            )

        mood_pulse = int(6 + 5 * (math.sin(self._anim_t * 5) + 1) * 0.5)
        edge = Image.new("RGBA", (SCR_W, SCR_H), (0, 0, 0, 0))
        edge_draw = ImageDraw.Draw(edge)
        edge_draw.rounded_rectangle(
            face_box,
            radius=PX * 3,
            outline=(glow_color[0], glow_color[1], glow_color[2], mood_pulse),
            width=1,
        )

        mask = Image.alpha_composite(mask, glow)
        mask = Image.alpha_composite(mask, glow2)
        mask = Image.alpha_composite(mask, expression)
        mask = Image.alpha_composite(mask, edge)
        return mask

    def _background(self, cx: int, cy: int) -> Image.Image:
        frame = Image.new("RGBA", (self._canvas_w, self._canvas_h), (0, 0, 0, 255))
        px = frame.load()
        max_dist = max(1, math.hypot(self._canvas_w / 2, self._canvas_h / 2))

        for y in range(self._canvas_h):
            for x in range(self._canvas_w):
                d = math.hypot(x - cx, y - cy) / max_dist
                v = int(5 + max(0, 1 - d * 1.4) * 13)
                px[x, y] = (v, v + 1, v + 5, 255)

        draw = ImageDraw.Draw(frame)
        for p in self._particles:
            alpha = int(80 * (1 - p["life"] / p["max"]))
            draw.rectangle((p["x"], p["y"], p["x"] + 1, p["y"] + 1), fill=(80, 95, 130, alpha))

        return frame

    def _composite_frame(self) -> Image.Image:
        self._rebuild_canvas()
        cx = self._canvas_w // 2
        cy = self._canvas_h // 2 + round(self._float_offset)

        frame = self._background(cx, cy)
        mask = self._render_mask()

        max_w = max(80, int(self._canvas_w * 0.72))
        max_h = max(70, int(self._canvas_h * 0.72))
        scale = min(max_w / SCR_W, max_h / SCR_H)
        target_w = max(48, int(SCR_W * scale))
        target_h = max(40, int(SCR_H * scale))
        resampling = Image.Resampling.NEAREST
        mask = mask.resize((target_w, target_h), resampling)

        hx = cx - target_w // 2
        hy = cy - target_h // 2
        frame.alpha_composite(mask, (hx, hy))
        return frame

    def _draw(self):
        try:
            frame = self._composite_frame()
            self._composite_tk = ImageTk.PhotoImage(frame)
            self._c.delete("all")
            self._c.create_image(0, 0, image=self._composite_tk, anchor="nw")
        except Exception as exc:
            print(f"face draw error: {exc}")
