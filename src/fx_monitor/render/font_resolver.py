"""Resolve a Japanese-capable font for matplotlib without bundling fonts.

Order of precedence:

1. ``FX_MONITOR_CJK_FONT_PATH`` — explicit path to a .ttf / .otf file.
2. ``FX_MONITOR_FONT_FAMILY``    — explicit installed family name.
3. First match in :data:`CJK_FONT_FAMILY_CANDIDATES` against installed fonts.

Never raises. Returns the selected family/path label, or ``None`` when no
CJK font could be resolved (in which case the caller may render with the
matplotlib default and accept tofu glyphs).
"""

from __future__ import annotations

import os
from pathlib import Path

CJK_FONT_FAMILY_CANDIDATES: list[str] = [
    "Noto Sans CJK JP",
    "Noto Sans JP",
    "IPAexGothic",
    "IPAGothic",
    "Yu Gothic",
    "YuGothic",
    "Hiragino Sans",
    "Hiragino Kaku Gothic ProN",
    "Meiryo",
]


def configure_matplotlib_japanese_font() -> str | None:
    """Configure matplotlib to use a Japanese-capable font if one is available."""
    try:
        import matplotlib.font_manager as fm
        import matplotlib.pyplot as plt
    except Exception:
        return None

    # 1. Explicit font file path.
    font_path = os.getenv("FX_MONITOR_CJK_FONT_PATH", "").strip()
    if font_path:
        p = Path(font_path)
        if p.exists() and p.is_file():
            try:
                fm.fontManager.addfont(str(p))
                family = fm.FontProperties(fname=str(p)).get_name()
                plt.rcParams["font.family"] = family
                plt.rcParams["axes.unicode_minus"] = False
                return family
            except Exception:
                pass

    # 2. Explicit family name.
    env_family = os.getenv("FX_MONITOR_FONT_FAMILY", "").strip()
    if env_family:
        plt.rcParams["font.family"] = env_family
        plt.rcParams["axes.unicode_minus"] = False
        return env_family

    # 3. Auto-detect from installed fonts.
    installed = {f.name for f in fm.fontManager.ttflist}
    for family in CJK_FONT_FAMILY_CANDIDATES:
        if family in installed:
            plt.rcParams["font.family"] = family
            plt.rcParams["axes.unicode_minus"] = False
            return family

    plt.rcParams["axes.unicode_minus"] = False
    return None


__all__ = [
    "CJK_FONT_FAMILY_CANDIDATES",
    "configure_matplotlib_japanese_font",
]
