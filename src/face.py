"""
Pixel art animation face — renders 24×20 pixel grid with
smooth cross-fade transitions, ambient glow, and floating.
"""

import tkinter as tk
import math
import random
from PIL import Image, ImageTk

from .moods import render_frame, MOODS, ORDER, BLACK, GLOW_AMBIENT, HLM_MAIN, HLM_HIGH, HLM_INNER

# ── Pixel scale: each logical pixel becomes PX × PX real pixels ──
PX = 6          # real pixels per logical pixel
GRID_W = 24     # logical columns
GRID_H = 20     # logical rows
SCR_W = GRID_W * PX    # 144
SCR_H = GRID_H * PX    # 120

# Helmet padding around the screen (in real pixels)
HELMET_PAD = 30
TOTAL_W = SCR_W + HELMET_PAD * 2   # 204
TOTAL_H = SCR_H + HELMET_PAD * 2   # 180

# ── Animation ──
FPS = 30
FRAME_MS = 1000 // FPS
FADE_FRAMES = 18   # ~600ms crossfade

BG_COLOR = "#0a0a14"


def _lerp_color(c1, c2, t):
    """Linear interpolate two RGBA tuples."""
    return tuple(round(a + (b - a) * t) for a, b in zip(c1, c2))


def _render_helmet(w, h):
    """Render helmet as PIL RGBA Image of given size."""
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    cx, cy = w // 2, h // 2

    # Outer glow
    for r in range(max(w, h) // 2, max(w, h) // 2 - 8, -1):
        alpha = max(0, 20 - (max(w, h) // 2 - r) * 3)
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                if dx * dx + dy * dy <= r * r:
                    # Only set if not overwritten
                    x, y = cx + dx, cy + dy
                    if 0 <= x < w and 0 <= y < h:
                        pr = img.getpixel((x, y))
                        if pr[3] < alpha:
                            img.putpixel((x, y), (GLOW_AMBIENT[0], GLOW_AMBIENT[1], GLOW_AMBIENT[2], alpha))

    # Helmet shell (rounded rect approximation)
    r_radius = 12
    for y in range(h):
        for x in range(w):
            dx = x - cx
            dy = y - cy
            hh = h // 2 - r_radius
            hw = w // 2 - r_radius
            # Rounded rect test
            if abs(dx) <= hw and abs(dy) <= hh:
                in_body = True
            elif abs(dx) <= hw and abs(dy) <= hh + r_radius:
                dy_c = abs(dy) - hh
                in_body = dx * dx + dy_c * dy_c <= r_radius * r_radius
            elif abs(dy) <= hh and abs(dx) <= hw + r_radius:
                dx_c = abs(dx) - hw
                in_body = dx_c * dx_c + dy * dy <= r_radius * r_radius
            else:
                dx_c = abs(dx) - hw
                dy_c = abs(dy) - hh
                in_body = dx_c <= r_radius and dy_c <= r_radius and \
                          dx_c * dx_c + dy_c * dy_c <= r_radius * r_radius

            if in_body:
                # Metallic gradient
                frac = (dy + h // 2) / h
                r_val = round(HLM_MAIN[0] + (HLM_HIGH[0] - HLM_MAIN[0]) * (1 - frac))
                g_val = round(HLM_MAIN[1] + (HLM_HIGH[1] - HLM_MAIN[1]) * (1 - frac))
                b_val = round(HLM_MAIN[2] + (HLM_HIGH[2] - HLM_MAIN[2]) * (1 - frac))
                # Edge highlight
                edge_dist = min(abs(dx) - hw + r_radius, abs(dy) - hh + r_radius)
                if edge_dist < 3 and edge_dist > 0:
                    r_val = min(255, r_val + 20)
                    g_val = min(255, g_val + 20)
                    b_val = min(255, b_val + 30)
                img.putpixel((x, y), (r_val, g_val, b_val, 255))

    # Inner screen border (dark panel)
    screen_cx = cx
    screen_cy = cy
    screen_w = SCR_W
    screen_h = SCR_H
    screen_x1 = screen_cx - screen_w // 2
    screen_y1 = screen_cy - screen_h // 2
    screen_x2 = screen_cx + screen_w // 2
    screen_y2 = screen_cy + screen_h // 2
    for y in range(screen_y1 - 2, screen_y2 + 3):
        for x in range(screen_x1 - 2, screen_x2 + 3):
            if 0 <= x < w and 0 <= y < h:
                if x < screen_x1 or x > screen_x2 or y < screen_y1 or y > screen_y2:
                    img.putpixel((x, y), HLM_INNER + (255,))

    return img


class Face:
    def __init__(self):
        self.state = "idle"
        self._mood = "calm"
        self._target_mood = "calm"

        # Render buffers
        self._helmet = None          # PIL Image
        self._helmet_tk = None
        self._composite = None       # PIL Image for current display
        self._composite_tk = None

        # Cross-fade state
        self._fading = False
        self._fade_frame = 0
        self._from_grid = None       # snapshot of grid when fade started
        self._to_mood = "calm"

        # Animation
        self._anim_t = 0.0
        self._float_offset = 0.0

        # Ambient particles
        self._particles = []

        # tkinter
        self._root = None
        self._c = None
        self._canvas_w = 800
        self._canvas_h = 600

    def setup(self):
        self._root = tk.Tk()
        self._root.title("小灵")
        self._root.configure(bg=BG_COLOR)
        self._root.attributes("-fullscreen", True)

        self._c = tk.Canvas(self._root, bg=BG_COLOR, highlightthickness=0)
        self._c.pack(fill="both", expand=True)

        # Pre-render helmet at a reasonable scale
        self._rebuild_canvas()

    def _rebuild_canvas(self):
        self._c.update_idletasks()
        self._canvas_w = self._c.winfo_width() or 800
        self._canvas_h = self._c.winfo_height() or 600
        self._helmet = _render_helmet(TOTAL_W, TOTAL_H)
        self._helmet_tk = ImageTk.PhotoImage(self._helmet)

    def set_state(self, state: str, mood: str = None):
        """Set face state and optionally set mood."""
        self.state = state
        if mood and mood in MOODS:
            self._set_mood(mood)

    def set_mood(self, mood: str):
        """Set expression mood, triggering cross-fade from current."""
        if mood in MOODS and mood != self._mood:
            self._set_mood(mood)

    def _set_mood(self, mood: str):
        # Snapshot current display as the "from" state
        if not self._fading:
            self._from_grid = render_frame(self._mood, self._anim_t)
        self._to_mood = mood
        self._fading = True
        self._fade_frame = 0
        self._target_mood = mood

    def get_mood(self) -> str:
        return self._mood

    def run(self):
        self._tick()
        self._root.mainloop()

    def _tick(self):
        self._anim_t = (self._anim_t + 0.03) % 100
        self._float_offset = math.sin(self._anim_t * 1.5) * 4

        # Update particles
        self._update_particles()

        # Finalize fade
        if self._fading:
            self._fade_frame += 1
            if self._fade_frame >= FADE_FRAMES:
                self._fading = False
                self._mood = self._to_mood

        self._draw()
        self._c.after(FRAME_MS, self._tick)

    def _update_particles(self):
        """Ambient floating particles."""
        if random.random() < 0.15:
            x = random.randint(-10, self._canvas_w + 10)
            speed = random.uniform(0.2, 0.6)
            size = random.randint(1, 2)
            alpha = random.randint(30, 80)
            self._particles.append({
                "x": x, "y": -5,
                "vx": random.uniform(-0.1, 0.1),
                "vy": speed,
                "size": size,
                "alpha": alpha,
                "life": 0,
            })

        dead = []
        for p in self._particles:
            p["x"] += p["vx"]
            p["y"] += p["vy"]
            p["life"] += 1
            if p["y"] > self._canvas_h + 10 or p["life"] > 300:
                dead.append(p)
        for p in dead:
            self._particles.remove(p)

    def _render_expression(self, mood: str, t: float) -> Image.Image:
        """Render a single expression frame as PIL Image (SCR_W × SCR_H)."""
        grid = render_frame(mood, t)
        img = Image.new("RGBA", (SCR_W, SCR_H), (0, 0, 0, 0))
        for y in range(GRID_H):
            for x in range(GRID_W):
                r, g, b, a = grid[y][x]
                if a > 0:
                    # Draw PX×PX block
                    for dy in range(PX):
                        for dx in range(PX):
                            img.putpixel((x * PX + dx, y * PX + dy), (r, g, b, a))
        return img

    def _composite_frame(self) -> Image.Image:
        """Build the full frame: screen + helmet + ambient glow."""
        t = self._anim_t

        if self._fading:
            # Blend between from_grid and target
            frac = self._fade_frame / FADE_FRAMES
            # Ease-in-out
            frac = frac * frac * (3 - 2 * frac)

            from_img = Image.new("RGBA", (SCR_W, SCR_H), (0, 0, 0, 0))
            for y in range(GRID_H):
                for x in range(GRID_W):
                    r, g, b, a = self._from_grid[y][x]
                    if a > 0:
                        for dy in range(PX):
                            for dx in range(PX):
                                from_img.putpixel((x * PX + dx, y * PX + dy), (r, g, b, a))

            to_img = self._render_expression(self._to_mood, t)
            screen = Image.blend(from_img, to_img, frac)
        else:
            screen = self._render_expression(self._mood, t)

        # Mood glow behind screen
        mood_info = MOODS.get(self._mood if not self._fading else self._to_mood, MOODS["calm"])
        glow_color = mood_info.get("glow", (40, 50, 80))
        glow_phase = (math.sin(t * 4) + 1) * 0.5
        glow_img = Image.new("RGBA", (SCR_W, SCR_H), (0, 0, 0, 0))
        glow_r = SCR_W // 2 + 8
        glow_alpha = int(20 + glow_phase * 30)
        for dy in range(-glow_r, glow_r + 1):
            for dx in range(-glow_r, glow_r + 1):
                if dx * dx + dy * dy <= glow_r * glow_r:
                    dist = math.sqrt(dx * dx + dy * dy) / glow_r
                    a = max(0, int(glow_alpha * (1 - dist)))
                    gx = SCR_W // 2 + dx
                    gy = SCR_H // 2 + dy
                    if 0 <= gx < SCR_W and 0 <= gy < SCR_H:
                        glow_img.putpixel((gx, gy),
                                          (glow_color[0], glow_color[1], glow_color[2], a))

        # Composite: glow → screen
        screen = Image.alpha_composite(glow_img, screen)

        # Place screen + helmet on canvas-sized frame
        # Helmet is TOTAL_W × TOTAL_H
        # Position centered on canvas with float offset
        cx = self._canvas_w // 2
        cy = self._canvas_h // 2 + round(self._float_offset)

        frame = Image.new("RGBA", (self._canvas_w, self._canvas_h), (0, 0, 0, 0))

        # Draw background (very subtle radial gradient)
        for y in range(self._canvas_h):
            for x in range(self._canvas_w):
                dx = x - cx
                dy = y - cy
                dist = math.sqrt(dx * dx + dy * dy) / max(self._canvas_w, self._canvas_h)
                bg_val = int(10 + max(0, 1 - dist * 1.5) * 10)
                frame.putpixel((x, y), (bg_val, bg_val, bg_val + 5, 255))

        # Draw particles
        for p in self._particles:
            px, py = int(p["x"]), int(p["y"])
            if 0 <= px < self._canvas_w and 0 <= py < self._canvas_h:
                frame.putpixel((px, py), (100, 120, 180, p["alpha"]))

        # Helmet position
        hx = cx - TOTAL_W // 2
        hy = cy - TOTAL_H // 2
        for y in range(TOTAL_H):
            for x in range(TOTAL_W):
                fx, fy = hx + x, hy + y
                if 0 <= fx < self._canvas_w and 0 <= fy < self._canvas_h:
                    pr, pg, pb, pa = self._helmet.getpixel((x, y))
                    if pa > 0:
                        frame.putpixel((fx, fy), (pr, pg, pb, 255))

        # Screen position inside helmet
        screen_offset_x = (TOTAL_W - SCR_W) // 2
        screen_offset_y = (TOTAL_H - SCR_H) // 2
        for y in range(SCR_H):
            for x in range(SCR_W):
                fx, fy = hx + screen_offset_x + x, hy + screen_offset_y + y
                if 0 <= fx < self._canvas_w and 0 <= fy < self._canvas_h:
                    pr, pg, pb, pa = screen.getpixel((x, y))
                    if pa > 0:
                        frame.putpixel((fx, fy), (pr, pg, pb, 255))

        # Status indicators (LED dots around helmet)
        status_colors = {
            "idle": (60, 60, 80),
            "listening": (0, 180, 255),
            "thinking": (255, 200, 50),
            "speaking": (0, 230, 100),
        }
        led_color = status_colors.get(self.state, (60, 60, 80))
        led_phase = (math.sin(t * 6) + 1) * 0.5
        for i in range(3):
            lx = hx - 6
            ly = hy + TOTAL_H // 2 + (i - 1) * 8
            led_r = int(led_color[0] * (0.5 + led_phase * 0.5))
            led_g = int(led_color[1] * (0.5 + led_phase * 0.5))
            led_b = int(led_color[2] * (0.5 + led_phase * 0.5))
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    if dx * dx + dy * dy <= 4:
                        fx, fy = lx + dx, ly + dy
                        if 0 <= fx < self._canvas_w and 0 <= fy < self._canvas_h:
                            frame.putpixel((fx, fy), (led_r, led_g, led_b, 255))

        return frame

    def _draw(self):
        try:
            frame = self._composite_frame()
            self._composite_tk = ImageTk.PhotoImage(frame)
            self._c.delete("all")
            self._c.create_image(0, 0, image=self._composite_tk, anchor="nw")
        except Exception:
            pass
