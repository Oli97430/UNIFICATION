"""Generates assets/logo.png + multi-size logo.ico for UNIFICATION.

Run once after editing:  python assets/make_logo.py

Design
------
Einstein side-profile silhouette (facing right) — a nod to the unified
field theory that inspired the app name.  Big puffy cloud of wild hair,
prominent nose, thick mustache, warm-white on dark gradient.  One accent
spark (top-right) hints at a "eureka" moment.
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


def _chaikin(pts: list[tuple[float, float]], iters: int = 2) -> list[tuple[float, float]]:
    """Chaikin corner-cutting subdivision — rounds sharp polygon corners."""
    for _ in range(iters):
        out: list[tuple[float, float]] = []
        for j in range(len(pts) - 1):
            ax, ay = pts[j]
            bx, by = pts[j + 1]
            out.append((0.75 * ax + 0.25 * bx, 0.75 * ay + 0.25 * by))
            out.append((0.25 * ax + 0.75 * bx, 0.25 * ay + 0.75 * by))
        pts = out
    return pts


# ---------------------------------------------------------------- Einstein

def _einstein_profile(s: int) -> list[tuple[float, float]]:
    """Clockwise polygon for Einstein's profile (facing right), canvas s x s."""

    # Cranium centre — anchor for parametric hair arc
    hcx, hcy = 0.40 * s, 0.44 * s

    # ---- face: collar -> chin -> mustache -> nose -> forehead ----
    face = [
        (0.54 * s, 0.86 * s),           # collar right
        (0.53 * s, 0.82 * s),
        (0.52 * s, 0.78 * s),           # throat
        (0.52 * s, 0.74 * s),
        (0.52 * s, 0.71 * s),           # chin
        (0.54 * s, 0.69 * s),
        (0.56 * s, 0.66 * s),
        (0.58 * s, 0.63 * s),           # lower lip
        # -- mustache --
        (0.62 * s, 0.61 * s),
        (0.66 * s, 0.59 * s),           # mustache tip
        (0.65 * s, 0.56 * s),
        (0.62 * s, 0.54 * s),
        # -- nose --
        (0.64 * s, 0.51 * s),
        (0.70 * s, 0.47 * s),           # NOSE TIP
        (0.66 * s, 0.44 * s),
        (0.63 * s, 0.42 * s),           # bridge
        # -- brow --
        (0.61 * s, 0.40 * s),
        (0.59 * s, 0.38 * s),           # brow ridge
        # -- forehead --
        (0.57 * s, 0.35 * s),
        (0.55 * s, 0.32 * s),
        (0.52 * s, 0.29 * s),           # hairline
    ]

    # ---- wild hair: big puffy cloud arc from forehead to back ----
    fx, fy = face[-1]                        # forehead connection
    bx, by = 0.20 * s, 0.44 * s             # back anchor (far left for volume)
    start_a = math.atan2(hcy - fy, fx - hcx)
    end_a   = math.atan2(hcy - by, bx - hcx)
    start_r = math.hypot(fx - hcx, fy - hcy)
    end_r   = math.hypot(bx - hcx, by - hcy)

    hair: list[tuple[float, float]] = []
    n = 120
    for i in range(1, n + 1):
        t = i / n  # 0 = forehead, 1 = back

        angle = start_a + (end_a - start_a) * t

        # Variable volume: modest at front, max at crown, generous at back
        # (quadratic bezier interpolation of three volume values)
        vol_front = 0.07                     # above forehead
        vol_crown = 0.24                     # top of head — biggest puff
        vol_back  = 0.15                     # behind head
        volume = (
            vol_front * (1 - t) ** 2
          + vol_crown * 2 * t * (1 - t)
          + vol_back  * t ** 2
        ) * s

        base = start_r + (end_r - start_r) * t + volume

        # Cloud-like undulation — very soft for round fluffy bumps
        wave = (
            0.018 * math.sin(i * 0.15 + 0.5)       # 2-3 broad pillowy puffs
          + 0.008 * math.sin(i * 0.38 + 1.4)       # gentle secondary
        ) * s

        env = 0.20 + 0.80 * math.sin(math.pi * t)  # taper at edges
        r = base + wave * env

        hair.append((hcx + r * math.cos(angle), hcy - r * math.sin(angle)))

    # Smooth the hair arc with Chaikin subdivision — 4 passes for pillow-soft curves
    hair = _chaikin(hair, iters=4)

    # ---- back of head + nape -> collar left ----
    back = [
        (0.20 * s, 0.50 * s),
        (0.20 * s, 0.56 * s),
        (0.22 * s, 0.62 * s),
        (0.24 * s, 0.68 * s),
        (0.27 * s, 0.73 * s),
        (0.30 * s, 0.78 * s),               # nape
        (0.34 * s, 0.83 * s),
        (0.37 * s, 0.86 * s),               # collar left
    ]

    return face + hair + back


# ---------------------------------------------------------------- logo

def build_logo(size: int = 512, *, with_spark: bool = True) -> Image.Image:
    s = size
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))

    # rounded gradient background
    bg = _vgradient((s, s), BG_TOP, BG_BOTTOM)
    bg.putalpha(_rounded_mask((s, s), radius=s // 6))
    img.alpha_composite(bg)

    # warm accent glow
    glow = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse(
        (int(0.15 * s), int(0.22 * s), int(0.68 * s), int(0.72 * s)),
        fill=(255, 122, 41, 35),
    )
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(s // 6)))

    # drop shadow
    profile = _einstein_profile(s)
    shadow_pts = [(x + s * 0.005, y + s * 0.007) for x, y in profile]
    shadow = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).polygon(shadow_pts, fill=(0, 0, 0, 50))
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(max(2, s // 28))))

    # Einstein silhouette
    layer = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ImageDraw.Draw(layer).polygon(profile, fill=INK)
    img.alpha_composite(layer)

    # accent spark (top-right)
    if with_spark and s >= 48:
        pad = s // 14
        r = max(3, s // 18)
        cx, cy = s - pad - r, pad + r
        halo = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        ImageDraw.Draw(halo).ellipse(
            (cx - r * 2, cy - r * 2, cx + r * 2, cy + r * 2),
            fill=(255, 122, 41, 80),
        )
        img.alpha_composite(halo.filter(ImageFilter.GaussianBlur(max(2, s // 40))))
        spark = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        ImageDraw.Draw(spark).ellipse(
            (cx - r, cy - r, cx + r, cy + r),
            fill=ACCENT, outline=INK, width=max(1, s // 180),
        )
        img.alpha_composite(spark)

    return img


# ---------------------------------------------------------------- entry point

def main() -> None:
    big = build_logo(512)
    big.save(HERE / "logo.png")
    print(f"  logo.png  ({HERE / 'logo.png'})")

    for sz in (128, 64, 32):
        src = build_logo(sz * 4, with_spark=(sz >= 48))
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
