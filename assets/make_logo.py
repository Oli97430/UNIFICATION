"""Generates assets/logo.png + multi-size logo.ico for UNIFICATION.

Run once after editing:  python assets/make_logo.py

Design
------
A central luminous node (the AI hub) surrounded by converging orbital
arcs — five paths flowing inward, representing the five creative apps
(Blender, FreeCAD, GIMP, Inkscape, Photoshop) unifying through a
single intelligent core.  Clean, geometric, modern.
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent

# Palette — keep in sync with gui/theme.py
BG_TOP    = (22, 26, 34, 255)
BG_BOTTOM = (40, 46, 60, 255)
ACCENT    = (255, 122, 41, 255)
INK       = (245, 240, 232, 255)

# App accent colours (matching _SUGGEST_APPS in app.py)
APP_COLORS = [
    (232, 125, 13),   # Blender  orange
    (217, 76, 76),    # FreeCAD  red
    (140, 140, 0),    # GIMP     olive-gold
    (63, 114, 175),   # Inkscape blue
    (49, 168, 255),   # Photoshop cyan
]


# ---------------------------------------------------------------- helpers

def _lerp(a, b, t):
    return tuple(int(a[i] * (1 - t) + b[i] * t) for i in range(len(a)))


def _vgradient(size, top, bottom):
    w, h = size
    col = Image.new("RGBA", (1, h))
    for y in range(h):
        col.putpixel((0, y), _lerp(top, bottom, y / max(h - 1, 1)))
    return col.resize((w, h))


def _rounded_mask(size, radius):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rounded_rectangle(
        (0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255,
    )
    return m


def _draw_thick_arc(draw, bbox, start_deg, end_deg, fill, width):
    """Draw an arc with the given width."""
    draw.arc(bbox, start_deg, end_deg, fill=fill, width=width)


def _draw_smooth_arc(img, cx, cy, radius, start_deg, end_deg, color, width, s):
    """Draw a smooth anti-aliased arc by plotting circles along the path."""
    layer = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    steps = max(60, int(abs(end_deg - start_deg) * 2))
    half_w = width / 2
    for i in range(steps + 1):
        t = i / steps
        angle = math.radians(start_deg + (end_deg - start_deg) * t)
        x = cx + radius * math.cos(angle)
        y = cy + radius * math.sin(angle)
        draw.ellipse(
            (x - half_w, y - half_w, x + half_w, y + half_w),
            fill=color,
        )
    img.alpha_composite(layer)


def _draw_converging_arc(img, cx, cy, r_start, r_end, angle_center,
                          arc_span, color, width_start, width_end, s, alpha=255):
    """Draw an arc that converges toward the center — gets thinner as it approaches."""
    layer = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    steps = 100
    half_span = arc_span / 2

    for i in range(steps + 1):
        t = i / steps  # 0=outer edge, 1=near center
        ease = t * t  # ease-in for smooth convergence

        radius = r_start + (r_end - r_start) * ease
        w = width_start + (width_end - width_start) * t
        spread = half_span * (1 - ease * 0.7)  # arc narrows as it converges
        angle = math.radians(angle_center + spread * math.sin(math.pi * t * 0.5))

        # Slight spiral twist
        angle = math.radians(angle_center) + (1 - ease) * math.radians(spread)

        x = cx + radius * math.cos(angle)
        y = cy + radius * math.sin(angle)

        a = int(alpha * (0.3 + 0.7 * t))  # fade in toward center
        col = (*color, a)
        hw = w / 2
        draw.ellipse((x - hw, y - hw, x + hw, y + hw), fill=col)

    img.alpha_composite(layer)


# ---------------------------------------------------------------- logo

def build_logo(size: int = 512) -> Image.Image:
    s = size
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    cx, cy = s / 2, s / 2

    # ---- rounded gradient background ----
    bg = _vgradient((s, s), BG_TOP, BG_BOTTOM)
    bg.putalpha(_rounded_mask((s, s), radius=s // 6))
    img.alpha_composite(bg)

    # ---- subtle radial glow behind center ----
    glow = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    gr = int(s * 0.32)
    ImageDraw.Draw(glow).ellipse(
        (cx - gr, cy - gr, cx + gr, cy + gr),
        fill=(255, 122, 41, 20),
    )
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(s // 5)))

    # ---- five converging flow-lines (one per app) ----
    angles = [90, 162, 234, 306, 18]  # evenly spaced, starting from top
    r_outer = s * 0.42
    r_inner = s * 0.10

    for i, base_angle in enumerate(angles):
        color = APP_COLORS[i]

        # Main flow arc — from outer edge toward center
        _draw_converging_arc(
            img, cx, cy,
            r_start=r_outer,
            r_end=r_inner,
            angle_center=base_angle,
            arc_span=35,
            color=color,
            width_start=max(2, s * 0.025),
            width_end=max(1, s * 0.008),
            s=s,
            alpha=200,
        )

        # Outer dot — the app node
        node_r = max(2, s * 0.022)
        nx = cx + r_outer * math.cos(math.radians(base_angle))
        ny = cy + r_outer * math.sin(math.radians(base_angle))

        # Node glow
        ng = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        ngr = node_r * 2.5
        ImageDraw.Draw(ng).ellipse(
            (nx - ngr, ny - ngr, nx + ngr, ny + ngr),
            fill=(*color, 60),
        )
        img.alpha_composite(ng.filter(ImageFilter.GaussianBlur(max(2, int(node_r * 1.5)))))

        # Solid node
        node = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        ImageDraw.Draw(node).ellipse(
            (nx - node_r, ny - node_r, nx + node_r, ny + node_r),
            fill=(*color, 255),
        )
        img.alpha_composite(node)

    # ---- orbital ring (thin, subtle) ----
    ring = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ring_r = s * 0.26
    ring_w = max(1, s * 0.004)
    _draw_smooth_arc(ring, cx, cy, ring_r, 0, 360, (*INK[:3], 35), ring_w, s)
    img.alpha_composite(ring)

    # Second ring slightly larger
    ring2 = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    _draw_smooth_arc(ring2, cx, cy, s * 0.34, 0, 360, (*INK[:3], 20), ring_w, s)
    img.alpha_composite(ring2)

    # ---- central core (the AI hub) ----
    # Outer glow
    core_glow = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    cgr = s * 0.12
    ImageDraw.Draw(core_glow).ellipse(
        (cx - cgr, cy - cgr, cx + cgr, cy + cgr),
        fill=(255, 140, 60, 50),
    )
    img.alpha_composite(core_glow.filter(ImageFilter.GaussianBlur(s // 8)))

    # Middle glow
    mid_glow = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    mgr = s * 0.07
    ImageDraw.Draw(mid_glow).ellipse(
        (cx - mgr, cy - mgr, cx + mgr, cy + mgr),
        fill=(255, 150, 80, 90),
    )
    img.alpha_composite(mid_glow.filter(ImageFilter.GaussianBlur(s // 14)))

    # Bright core
    core = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    cr = s * 0.04
    ImageDraw.Draw(core).ellipse(
        (cx - cr, cy - cr, cx + cr, cy + cr),
        fill=ACCENT,
    )
    img.alpha_composite(core)

    # White-hot center
    hot = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    hr = s * 0.018
    ImageDraw.Draw(hot).ellipse(
        (cx - hr, cy - hr, cx + hr, cy + hr),
        fill=INK,
    )
    img.alpha_composite(hot)

    return img


# ---------------------------------------------------------------- entry point

def main() -> None:
    big = build_logo(512)
    big.save(HERE / "logo.png")
    print(f"  logo.png  ({HERE / 'logo.png'})")

    for sz in (256, 128, 96, 64, 48, 32, 16):
        src = build_logo(max(sz * 4, 512))
        src.resize((sz, sz), Image.LANCZOS).save(HERE / f"logo_{sz}.png")
        print(f"  logo_{sz}.png")

    big.save(
        HERE / "logo.ico",
        sizes=[
            (16, 16), (24, 24), (32, 32),
            (48, 48), (64, 64), (128, 128), (256, 256),
        ],
    )
    print(f"  logo.ico")


if __name__ == "__main__":
    main()
