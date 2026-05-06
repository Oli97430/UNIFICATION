"""Shared design tokens — keep colors / radii / fonts consistent across views."""
from __future__ import annotations

# Palette
ACCENT = "#FF7A29"
ACCENT_HOVER = "#FF9450"
ACCENT_MUTED = "#7A3B14"

BG_BASE = "#181C24"
BG_PANEL = "#21262F"
BG_RAISED = "#2A303B"
BG_INPUT = "#1B1F27"

INK = "#E6ECF5"
INK_MUTED = "#9AA3B2"
INK_DIM = "#6F7787"

OK = "#34D399"
WARN = "#F59E0B"
ERR = "#F87171"

EDGE = "#323844"

# Radii
R_SM = 8
R_MD = 12
R_LG = 18

# Type
FONT_FAMILY = "Segoe UI"  # Windows; falls back gracefully on other OSes
FONT_MONO = "Consolas"

# Font scale — semantic sizes used across the app. Bump all of these together
# to grow / shrink the UI uniformly.
FS_TINY = 11      # legends, "MODEL" header, hover ms text
FS_DIM = 12       # path, version, secondary
FS_BODY = 13      # default body text
FS_INPUT = 14     # entries / textboxes
FS_TITLE = 15     # card titles
FS_HEAD = 22      # window-level titles ("UNIFICATION" header)
FS_PAGE = 24      # view headlines ("Models", "Setup", …)
FS_HERO = 26      # empty-state hero
FS_HERO_BIG = 28  # about page hero
