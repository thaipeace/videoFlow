"""Scrolling news ticker (right -> left) rendered along the bottom of the frame.

The text strip is pre-rendered once with Pillow as a transparent PNG made of several identical
copies of the ticker text. FFmpeg slides it left with ``x = X0 - mod((t + offset) * speed, loop)``;
because the copies are identical the wrap-around is seamless, and ``offset`` (the slide's start
time in the video) keeps the scroll continuous across independently rendered slides.
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import List, Optional

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

SEPARATOR = "   \u2022   "
BADGE_COLOR = (214, 30, 38)
BAR_FILL = "0x0A0A0F@0.86"
ACCENT_FILL = "0xD61E26@0.95"
MAX_LOOP_PX = 14000  # one copy; the strip holds >= 2 copies, staying below PNG/FFmpeg size limits
SPEED_BASE_RATIO = 0.12  # px/s per px of the short side (~130 px/s at 1080p)

_BOLD_FONT_CANDIDATES = (
    "segoeuib.ttf",
    "arialbd.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "DejaVuSans-Bold.ttf",
)


def _bold_font(size: int) -> ImageFont.ImageFont:
    for name in _BOLD_FONT_CANDIDATES:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    logger.warning("No bold TrueType font found for the news ticker; using Pillow default.")
    return ImageFont.load_default()


@dataclass(frozen=True)
class TickerSpec:
    """Pre-rendered ticker assets plus the geometry FFmpeg needs to composite them."""

    strip_path: Path
    badge_path: Path
    width: int
    bar_y: int
    bar_h: int
    strip_x: int
    loop_px: int
    speed: float
    start_offset: float = 0.0

    def with_offset(self, seconds: float) -> "TickerSpec":
        return replace(self, start_offset=max(0.0, float(seconds)))

    def drawbox_filters(self) -> List[str]:
        """Static bar background and thin red accent line (no extra input needed)."""
        return [
            f"drawbox=x=0:y={self.bar_y}:w={self.width}:h={self.bar_h}:color={BAR_FILL}:t=fill",
            f"drawbox=x=0:y={self.bar_y}:w={self.width}:h=3:color={ACCENT_FILL}:t=fill",
        ]

    def scroll_overlay(self) -> str:
        """Overlay filter (without pad labels) that scrolls the strip right -> left."""
        x_expr = f"{self.strip_x}-mod((t+{self.start_offset:.3f})*{self.speed:.3f},{self.loop_px})"
        return f"overlay=x='{x_expr}':y={self.bar_y}:format=auto"


def split_ticker_items(text: str) -> List[str]:
    """Split ticker text on '|' separators into clean headline items."""
    return [re.sub(r"\s+", " ", part).strip(" .,;:-") for part in re.split(r"\s*\|\s*", str(text or "")) if part.strip()]


def _bar_geometry(width: int, height: int) -> tuple[int, int, int]:
    base = min(width, height)
    bar_h = max(36, round(base * 0.062))
    # Landscape: flush with the bottom edge. Portrait: lifted above the YouTube Shorts UI zone.
    bar_bottom = height if width >= height else int(height * 0.84)
    return base, bar_h, bar_bottom - bar_h


def build_ticker(
    width: int,
    height: int,
    text: str,
    cache_dir: Path,
    label: str = "TIN MỚI",
) -> Optional[TickerSpec]:
    """Render the scrolling strip and the static label badge. Returns None when there is no text."""
    items = split_ticker_items(text)
    if not items:
        return None

    base, bar_h, bar_y = _bar_geometry(width, height)
    font = _bold_font(max(14, round(bar_h * 0.50)))
    badge_font = _bold_font(max(12, round(bar_h * 0.44)))
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))

    def unit_width(parts: List[str]) -> int:
        return int(math.ceil(probe.textlength("".join(f"{p}{SEPARATOR}" for p in parts), font=font)))

    while unit_width(items) > MAX_LOOP_PX and len(items) > 1:
        items = items[:-1]
    unit = "".join(f"{p}{SEPARATOR}" for p in items)
    loop_px = max(1, unit_width(items))

    # Badge (opaque, drawn on top of the strip so scrolling text disappears underneath it).
    label_text = (label or "TIN MỚI").strip().upper()
    badge_w_text = int(math.ceil(probe.textlength(label_text, font=badge_font)))
    pad = round(bar_h * 0.45)
    badge_w = badge_w_text + pad * 2
    badge = Image.new("RGBA", (badge_w, bar_h), (0, 0, 0, 0))
    bdraw = ImageDraw.Draw(badge)
    bdraw.rectangle((0, 3, badge_w, bar_h), fill=(*BADGE_COLOR, 255))
    bdraw.text((badge_w / 2, (bar_h + 3) / 2), label_text, font=badge_font, fill=(255, 255, 255, 255), anchor="mm")

    strip_x = badge_w + round(bar_h * 0.30)
    copies = int(math.ceil((width - strip_x) / loop_px)) + 1
    strip = Image.new("RGBA", (loop_px * copies, bar_h), (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(strip)
    mid = (bar_h + 3) / 2
    for i in range(copies):
        x = i * loop_px
        sdraw.text((x + 1, mid + 1), unit, font=font, fill=(0, 0, 0, 150), anchor="lm")
        sdraw.text((x, mid), unit, font=font, fill=(255, 255, 255, 255), anchor="lm")

    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    strip_path = cache_dir / "ticker_strip.png"
    badge_path = cache_dir / "ticker_badge.png"
    strip.save(strip_path, format="PNG", compress_level=1)
    badge.save(badge_path, format="PNG")

    return TickerSpec(
        strip_path=strip_path,
        badge_path=badge_path,
        width=width,
        bar_y=bar_y,
        bar_h=bar_h,
        strip_x=strip_x,
        loop_px=loop_px,
        speed=round(base * SPEED_BASE_RATIO, 3),
    )
