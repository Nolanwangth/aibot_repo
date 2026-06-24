"""
Pixel art mood definitions + animation engine.
Each mood is a set of drawing commands on a 24×20 pixel grid.
"""

# ── Color Palette ──────────────────────────────────────────────
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)

# Neon hues for expressions
BLUE = (0, 160, 255)
RED = (255, 60, 60)
PINK = (255, 60, 180)
GREEN = (0, 230, 100)
YELLOW = (255, 220, 50)
PURPLE = (180, 60, 255)
ORANGE = (255, 160, 20)
CYAN = (0, 220, 255)
SOFT_WARM = (255, 200, 150)
TEAL = (0, 200, 180)

# Helmet + UI colors
HLM_MAIN = (35, 40, 55)
HLM_EDGE = (60, 65, 85)
HLM_HIGH = (100, 110, 140)
HLM_INNER = (15, 18, 30)
GLOW_AMBIENT = (40, 50, 80)

# ── Mood Definitions ───────────────────────────────────────────

MOODS = {
    "calm": {
        "name": "冷静",
        "color": BLUE,
        "glow": (0, 80, 180),
    },
    "happy": {
        "name": "开心",
        "color": GREEN,
        "glow": (0, 120, 60),
    },
    "thinking": {
        "name": "思考",
        "color": WHITE,
        "glow": (60, 60, 80),
    },
    "excited": {
        "name": "激动",
        "color": YELLOW,
        "glow": (180, 150, 0),
    },
    "confused": {
        "name": "困惑",
        "color": PURPLE,
        "glow": (100, 30, 140),
    },
    "surprised": {
        "name": "惊讶",
        "color": CYAN,
        "glow": (0, 120, 180),
    },
    "focused": {
        "name": "专注",
        "color": RED,
        "glow": (140, 20, 20),
    },
    "angry": {
        "name": "愤怒",
        "color": RED,
        "glow": (160, 25, 10),
    },
    "sad": {
        "name": "伤心",
        "color": BLUE,
        "glow": (20, 40, 100),
    },
    "afraid": {
        "name": "害怕",
        "color": YELLOW,
        "glow": (140, 110, 20),
    },
    "playful": {
        "name": "调皮",
        "color": PINK,
        "glow": (140, 30, 100),
    },
    "lovestruck": {
        "name": "花痴",
        "color": PINK,
        "glow": (150, 35, 110),
    },
    "cool": {
        "name": "装酷",
        "color": PURPLE,
        "glow": (95, 30, 150),
    },
    "soothing": {
        "name": "治愈",
        "color": SOFT_WARM,
        "glow": (140, 100, 60),
    },
    "sleepy": {
        "name": "困倦",
        "color": TEAL,
        "glow": (20, 90, 80),
    },
}

ORDER = ["calm", "happy", "thinking", "excited", "confused", "surprised",
         "focused", "angry", "sad", "afraid", "playful", "lovestruck",
         "cool", "soothing", "sleepy"]


# ── Pixel Drawing Engine ────────────────────────────────────────

def _set(grid, x, y, color):
    """Set one logical pixel."""
    if 0 <= x < 24 and 0 <= y < 20:
        grid[y][x] = color


def _hline(grid, y, x1, x2, color):
    for x in range(min(x1, x2), max(x1, x2) + 1):
        _set(grid, x, y, color)


def _vline(grid, x, y1, y2, color):
    for y in range(min(y1, y2), max(y1, y2) + 1):
        _set(grid, x, y, color)


def _rect(grid, x1, y1, x2, y2, color):
    for y in range(y1, y2 + 1):
        for x in range(x1, x2 + 1):
            _set(grid, x, y, color)


def _circle(grid, cx, cy, r, color):
    """Draw filled circle."""
    for y in range(cy - r, cy + r + 1):
        for x in range(cx - r, cx + r + 1):
            if (x - cx) ** 2 + (y - cy) ** 2 <= r ** 2:
                _set(grid, x, y, color)


def _arc(grid, cx, cy, w, h, start_deg, end_deg, color):
    """Draw an arc (for mouth shapes). Simple Bresenham ellipse arc."""
    import math
    for deg in range(start_deg, end_deg + 1):
        rad = math.radians(deg)
        x = round(cx + w * math.cos(rad))
        y = round(cy + h * math.sin(rad))
        _set(grid, x, y, color)


def _blush(grid, x, y, color, intensity=1):
    """Subtle blush dots."""
    for dy in range(-1, 2):
        for dx in range(-1, 2):
            _set(grid, x + dx, y + dy, color)


# ── Expression Drawers ─────────────────────────────────────────
# Each function draws onto a 24x20 grid.
# t = 0..1 animation phase (for blinking, glowing, etc.)


def _draw_eyes_round(grid, lx, ly, rx, ry, color):
    """Standard round eyes."""
    _circle(grid, lx, ly, 2, color)
    _circle(grid, rx, ry, 2, color)
    # Pupils
    _set(grid, lx, ly, BLACK)
    _set(grid, rx, ry, BLACK)


def _draw_eyes_horizontal(grid, lx, ly, rx, ry, color, length=3):
    """Horizontal line eyes (calm/stoic)."""
    _hline(grid, ly, lx - length, lx + length, color)
    _hline(grid, ry, rx - length, rx + length, color)


def _draw_eyes_angry(grid, lx, ly, rx, ry, color):
    """Angry V-eyebrow + dot eyes."""
    # Eyebrow V's
    _hline(grid, ly - 2, lx - 1, lx + 1, color)
    _hline(grid, ry - 2, rx - 1, rx + 1, color)
    # Dot eyes
    _set(grid, lx, ly, color)
    _set(grid, rx, ry, color)


def _draw_eyes_heart(grid, lx, ly, rx, ry, color):
    """Heart eyes (love-struck)."""
    for cx, cy in [(lx, ly), (rx, ry)]:
        for y in range(cy - 2, cy + 2):
            for x in range(cx - 2, cx + 2):
                dx, dy = x - cx, y - cy
                # Heart equation
                d = (dx * dx + dy * dy - 4) ** 3
                if (dx * dx + dy * dy - 4) ** 3 - dx * dx * dy * dy * dy <= 0:
                    _set(grid, x, y, color)


def _draw_eyes_star(grid, lx, ly, rx, ry, color):
    """Star eyes (excited)."""
    for cx, cy in [(lx, ly), (rx, ry)]:
        _circle(grid, cx, cy, 2, color)
        for i in range(4):
            import math
            a = math.radians(i * 90 + 45)
            _set(grid, cx + round(math.cos(a) * 3),
                 cy + round(math.sin(a) * 3), color)


def _draw_eyes_wavy(grid, lx, ly, rx, ry, color):
    """Wavy/zigzag eyes (confused/thinking)."""
    # Left eye: dot
    _circle(grid, lx, ly, 1, color)
    # Right eye: zigzag
    for dx in range(-2, 3):
        zig_y = ry + (dx % 2) - 1
        _set(grid, rx + dx, zig_y, color)


def _draw_eyes_big(grid, lx, ly, rx, ry, color):
    """Big round eyes (surprised)."""
    _circle(grid, lx, ly, 3, color)
    _circle(grid, rx, ry, 3, color)
    _circle(grid, lx, ly, 1, WHITE)
    _circle(grid, rx, ry, 1, WHITE)


def _draw_eyes_slit(grid, lx, ly, rx, ry, color):
    """Narrow slit eyes (focused)."""
    _hline(grid, ly, lx - 1, lx + 1, color)
    _hline(grid, ry, rx - 1, rx + 1, color)


def _draw_eyes_teardrop(grid, lx, ly, rx, ry, color):
    """Tear-drop sad eyes."""
    for cx, cy in [(lx, ly), (rx, ry)]:
        _circle(grid, cx, cy, 1, color)
        _set(grid, cx - 1, cy + 2, color)


def _draw_eyes_wink(grid, lx, ly, rx, ry, phase):
    """Winking eye (playful). Uses phase for blink."""
    if phase < 0.3:
        # Both open with different shapes
        _circle(grid, lx, ly, 2, PINK)
        _hline(grid, ry, rx - 2, rx + 2, PINK)  # wink
    else:
        _circle(grid, lx, ly, 2, PINK)
        _circle(grid, rx, ry, 2, PINK)


def _draw_eyes_soft(grid, lx, ly, rx, ry, color):
    """Soft gentle eyes (soothing)."""
    _circle(grid, lx, ly, 2, color)
    _circle(grid, rx, ry, 2, color)
    # Half-closed
    _hline(grid, ly - 1, lx - 2, lx + 2, color)
    _hline(grid, ry - 1, rx - 2, rx + 2, color)


def _draw_eyes_sleepy(grid, lx, ly, rx, ry, color, phase):
    """Sleepy droopy eyes."""
    open_amt = max(0, 1 - phase * 2)
    if open_amt > 0.3:
        _hline(grid, ly, lx - 1, lx + 1, color)
        _hline(grid, ry, rx - 1, rx + 1, color)
    else:
        _hline(grid, ly + 1, lx - 2, lx + 2, color)
        _hline(grid, ry + 1, rx - 2, rx + 2, color)


def _draw_sunglasses(grid, lx, ly, rx, ry, color):
    for cx in (lx, rx):
        _hline(grid, ly - 1, cx - 3, cx + 3, color)
        _hline(grid, ly, cx - 3, cx + 3, color)
        _set(grid, cx - 2, ly + 1, color)
        _set(grid, cx - 1, ly + 1, color)
        _set(grid, cx + 1, ly + 1, color)
        _set(grid, cx + 2, ly + 1, color)
    _hline(grid, ly - 1, lx + 4, rx - 4, color)


def _draw_mouth_smile(grid, cx, cy, color, width=4):
    """Curved smile."""
    for x in range(cx - width, cx + width + 1):
        t = (x - cx) / width
        y = cy + round(2 * (1 - t * t))  # parabola arc
        _set(grid, x, y, color)


def _draw_mouth_open(grid, cx, cy, color, wide=3):
    """Open mouth (surprise/happy)."""
    _rect(grid, cx - wide, cy - 1, cx + wide, cy + 2, color)
    if wide >= 3:
        _set(grid, cx - wide + 1, cy, BLACK)
        _set(grid, cx, cy, BLACK)
        _set(grid, cx + wide - 1, cy, BLACK)


def _draw_mouth_line(grid, cx, cy, color, length=3):
    """Straight line mouth."""
    _hline(grid, cy, cx - length, cx + length, color)


def _draw_mouth_frown(grid, cx, cy, color, width=3):
    """Frown (sad)."""
    for x in range(cx - width, cx + width + 1):
        t = (x - cx) / width
        y = cy + round(2 * (t * t) - 1)  # inverted parabola
        _set(grid, x, y, color)


def _draw_mouth_wavy(grid, cx, cy, color, width=4):
    """Wavy/afraid mouth."""
    for dx in range(-width, width + 1):
        zig_y = cy + (abs(dx) % 3) - 1
        _set(grid, cx + dx, zig_y, color)


def _draw_mouth_smirk(grid, cx, cy, color, width=3):
    """Smirk (one side up)."""
    for x in range(cx - width, cx + width + 1):
        t = (x - cx) / width
        tilt = 0.5 if x > cx else 0
        y = cy + round(2 * (1 - t * t) - tilt)
        _set(grid, x, y, color)


def _draw_brow_angry(grid, lx, ly, rx, ry, color):
    _set(grid, lx - 3, ly - 3, color)
    _set(grid, lx - 2, ly - 2, color)
    _set(grid, lx - 1, ly - 2, color)
    _set(grid, lx, ly - 1, color)
    _set(grid, rx + 3, ry - 3, color)
    _set(grid, rx + 2, ry - 2, color)
    _set(grid, rx + 1, ry - 2, color)
    _set(grid, rx, ry - 1, color)


# ── Mood Renderers ──────────────────────────────────────────────
# Each render(grid, t) function draws the full expression.
# Eye centers: left=(7,8), right=(17,8)
# Mouth center: (12, 15)
# t = animation phase 0..1 (for blinking/breathing)

LX, LY = 7, 8
RX, RY = 17, 8
MX, MY = 12, 15


def _render_calm(grid, t):
    col = BLUE
    _draw_eyes_horizontal(grid, LX, LY, RX, RY, col, length=3)
    _draw_mouth_line(grid, MX, MY, col, length=4)
    # Subtle glow in eyes
    phase = t * 6.28
    glow = int(abs(phase) * 40)
    _set(grid, LX + 1, LY, (col[0] + glow, col[1] + glow, 255))
    _set(grid, RX - 1, RY, (col[0] + glow, col[1] + glow, 255))


def _render_happy(grid, t):
    col = GREEN
    _draw_eyes_round(grid, LX, LY, RX, RY, col)
    # eyes slightly curved up
    _hline(grid, LY - 1, LX - 2, LX + 2, col)
    _hline(grid, RY - 1, RX - 2, RX + 2, col)
    _draw_mouth_open(grid, MX, MY, col, wide=3)
    # Blush
    _blush(grid, LX - 3, LY + 1, (col[0] // 3, col[1], col[2] // 3), 1)
    _blush(grid, RX + 3, RY + 1, (col[0] // 3, col[1], col[2] // 3), 1)


def _render_thinking(grid, t):
    col = WHITE
    _draw_eyes_round(grid, LX, LY, RX, RY, col)
    # Asymmetric - one eye looking up
    _set(grid, LX, LY - 1, (0, 0, 0))
    _set(grid, RX, RY, (0, 0, 0))
    _draw_mouth_line(grid, MX, MY, col, length=2)
    # Question mark flickering
    if int(t * 4) % 3 != 0:
        _set(grid, MX + 3, MY - 5, col)
        _set(grid, MX + 3, MY - 4, col)
        _set(grid, MX + 3, MY - 1, col)


def _render_excited(grid, t):
    col = YELLOW
    _draw_eyes_star(grid, LX, LY, RX, RY, col)
    _draw_mouth_open(grid, MX, MY, col, wide=4)
    # Radiating lines
    for i, (ex, ey) in enumerate([(LX, LY), (RX, RY)]):
        phase = t * 6.28 + i
        for a in range(0, 360, 90):
            import math
            rad = math.radians(a + phase * 30)
            sx = ex + round(math.cos(rad) * 5)
            sy = ey + round(math.sin(rad) * 5)
            _set(grid, sx, sy, col)


def _render_confused(grid, t):
    col = PURPLE
    _draw_eyes_wavy(grid, LX, LY, RX, RY, col)
    _draw_mouth_line(grid, MX, MY, col, length=3)
    # Question marks
    if int(t * 3) % 2 == 0:
        _set(grid, MX + 4, MY - 6, WHITE)
        _set(grid, MX + 4, MY - 5, WHITE)
        _set(grid, MX + 4, MY - 2, WHITE)


def _render_surprised(grid, t):
    col = CYAN
    _draw_eyes_big(grid, LX, LY, RX, RY, col)
    _draw_mouth_open(grid, MX, MY, col, wide=3)
    # Exclamation mark
    _vline(grid, MX + 5, MY - 6, MY - 3, col)
    _set(grid, MX + 5, MY - 1, col)


def _render_focused(grid, t):
    col = RED
    _draw_eyes_slit(grid, LX, LY, RX, RY, col)
    _draw_mouth_line(grid, MX, MY, col, length=3)
    # Scanning horizontal line
    scan_y = 4 + int((t * 20) % 12)
    _hline(grid, scan_y, LX - 2, RX + 2,
           (col[0], col[1] // 4, col[2] // 4))


def _render_angry(grid, t):
    col = RED
    _draw_brow_angry(grid, LX, LY, RX, RY, col)
    _hline(grid, LY, LX - 1, LX + 2, col)
    _hline(grid, RY, RX - 2, RX + 1, col)
    _draw_mouth_frown(grid, MX, MY, col, width=4)
    if int(t * 10) % 2 == 0:
        _set(grid, LX + 3, LY - 1, ORANGE)
        _set(grid, RX - 3, RY - 1, ORANGE)


def _render_sad(grid, t):
    col = BLUE
    _draw_eyes_teardrop(grid, LX, LY, RX, RY, col)
    _draw_mouth_frown(grid, MX, MY, col, width=3)
    # Tear drops (animated)
    if t % 0.5 > 0.3:
        tear_y = LY + 3 + int(t * 4) % 3
        _set(grid, LX, tear_y, CYAN)
        _set(grid, RX, tear_y, CYAN)


def _render_afraid(grid, t):
    col = YELLOW
    _draw_eyes_big(grid, LX, LY, RX, RY, col)
    shake = -1 if int(t * 12) % 2 == 0 else 1
    _draw_mouth_wavy(grid, MX + shake, MY + 1, col, width=4)
    _hline(grid, LY - 3, LX - 2, LX + 2, col)
    _hline(grid, RY - 3, RX - 2, RX + 2, col)


def _render_playful(grid, t):
    col = PINK
    _draw_eyes_wink(grid, LX, LY, RX, RY, t)
    _draw_mouth_smirk(grid, MX, MY, col, width=3)
    # Sparkle
    sparkle = int(t * 6) % 3
    if sparkle == 0:
        _set(grid, LX + 3, LY - 3, WHITE)
        _set(grid, LX + 3, LY - 4, WHITE)
        _set(grid, LX + 4, LY - 3, WHITE)


def _render_lovestruck(grid, t):
    col = PINK
    _draw_eyes_heart(grid, LX, LY, RX, RY, col)
    _draw_mouth_smile(grid, MX, MY, col, width=3)
    if int(t * 6) % 2 == 0:
        _set(grid, LX - 4, LY + 3, col)
        _set(grid, RX + 4, RY + 3, col)


def _render_cool(grid, t):
    col = PURPLE
    _draw_sunglasses(grid, LX, LY, RX, RY, col)
    _draw_mouth_smirk(grid, MX, MY, col, width=3)
    shine_x = LX - 2 + int(t * 8) % 5
    _set(grid, shine_x, LY - 1, WHITE)


def _render_soothing(grid, t):
    col = SOFT_WARM
    _draw_eyes_soft(grid, LX, LY, RX, RY, col)
    _draw_mouth_smile(grid, MX, MY, col, width=4)
    # Warm glow dots
    phase = t * 6.28
    dot_y = LY + int(abs(phase) % 4)
    _set(grid, MX - 1, MY + 2, ORANGE)
    _set(grid, MX + 1, MY + 2, ORANGE)


def _render_sleepy(grid, t):
    col = TEAL
    _draw_eyes_sleepy(grid, LX, LY, RX, RY, col, t)
    _draw_mouth_line(grid, MX, MY + 1, col, length=2)
    # Z's floating up
    z_offset = int(t * 4) % 8
    for i in range(3):
        zy = MY - 6 - z_offset + i * 3
        if 0 <= zy < 20:
            _set(grid, MX + 3 + i, zy, TEAL)
            _set(grid, MX + 3 + i + 1, zy, TEAL)


# ── Render Dispatch ─────────────────────────────────────────────

RENDERERS = {
    "calm": _render_calm,
    "happy": _render_happy,
    "thinking": _render_thinking,
    "excited": _render_excited,
    "confused": _render_confused,
    "surprised": _render_surprised,
    "focused": _render_focused,
    "angry": _render_angry,
    "sad": _render_sad,
    "afraid": _render_afraid,
    "playful": _render_playful,
    "lovestruck": _render_lovestruck,
    "cool": _render_cool,
    "soothing": _render_soothing,
    "sleepy": _render_sleepy,
}


def render_frame(mood: str, t: float) -> list:
    """Render one animation frame. Returns 20x24 list of (R,G,B,A) tuples."""
    grid = [[BLACK for _ in range(24)] for _ in range(20)]
    renderer = RENDERERS.get(mood, _render_calm)
    renderer(grid, t)
    # Convert plain color to RGBA
    rendered = []
    for row in grid:
        rendered_row = []
        for pixel in row:
            r, g, b = pixel[:3]
            # Determine alpha: if exact black, transparent
            if pixel == BLACK or (len(pixel) == 4 and pixel[3] == 0):
                rendered_row.append((r, g, b, 0))
            else:
                rendered_row.append((r, g, b, 255))
        rendered.append(rendered_row)
    return rendered
