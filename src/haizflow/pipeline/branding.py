"""Channel branding overlay (Vạn Chuyện): tiny VCH logo + faint random-slot watermark.

The overlay is a full-frame transparent PNG built with Pillow and composited onto each
rendered slide by FFmpeg, so it needs no drawtext/font support in the FFmpeg build.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

LOGO_TEXT = "VCH"
WATERMARK_TEXT = "VẠN CHUYỆN"
LOGO_COLOR = (214, 30, 38)
LOGO_OPACITY = 0.88
WATERMARK_OPACITY = 0.16

# Horizontal slots for the faint watermark; the vertical position is fixed per orientation.
WATERMARK_SLOTS: Tuple[str, ...] = ("right", "center", "left_inner", "right_inner")

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
    logger.warning("No bold TrueType font found for branding overlay; using Pillow default.")
    return ImageFont.load_default()


def _text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> Tuple[int, int]:
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    return right - left, bottom - top


def _watermark_origin(slot: str, width: int, height: int, text_w: int) -> Tuple[int, int]:
    base = min(width, height)
    # Landscape: sits just above the future ticker bar. Portrait: above the Shorts UI zone.
    y = height - int(base * 0.13) if width >= height else int(height * 0.74)
    margin = int(base * 0.06)
    if slot == "center":
        x = (width - text_w) // 2
    elif slot == "left_inner":
        x = int(width * 0.18)
    elif slot == "right_inner":
        x = width - text_w - int(width * 0.18)
    else:  # "right"
        x = width - text_w - margin
    return max(0, x), y


def build_branding_overlay(
    width: int,
    height: int,
    output_path: Path,
    watermark_slot: str = "right",
) -> Path:
    """Render a transparent full-frame PNG with the small VCH logo (top-left) and faint watermark."""
    base = min(width, height)
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Logo badge: deliberately tiny (~2.3% of the short side tall).
    badge_h = max(18, round(base * 0.023))
    logo_font = _bold_font(max(10, round(badge_h * 0.62)))
    text_w, text_h = _text_size(draw, LOGO_TEXT, logo_font)
    pad_x = round(badge_h * 0.45)
    badge_w = text_w + pad_x * 2
    margin = round(base * 0.025)
    alpha = round(255 * LOGO_OPACITY)
    draw.rounded_rectangle(
        (margin, margin, margin + badge_w, margin + badge_h),
        radius=max(2, round(badge_h * 0.2)),
        fill=(*LOGO_COLOR, alpha),
    )
    draw.text(
        (margin + (badge_w - text_w) / 2, margin + (badge_h - text_h) / 2 - round(badge_h * 0.06)),
        LOGO_TEXT,
        font=logo_font,
        fill=(255, 255, 255, 255),
    )

    # Faint watermark: low alpha white with an even fainter shadow for legibility on bright photos.
    wm_font = _bold_font(max(12, round(base * 0.022)))
    wm_w, _ = _text_size(draw, WATERMARK_TEXT, wm_font)
    wx, wy = _watermark_origin(watermark_slot, width, height, wm_w)
    shadow = round(255 * WATERMARK_OPACITY * 0.6)
    draw.text((wx + 1, wy + 1), WATERMARK_TEXT, font=wm_font, fill=(0, 0, 0, shadow))
    draw.text((wx, wy), WATERMARK_TEXT, font=wm_font, fill=(255, 255, 255, round(255 * WATERMARK_OPACITY)))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    overlay.save(output_path, format="PNG")
    return output_path


class BrandingOverlayPool:
    """Lazily builds one overlay PNG per watermark slot and picks slots randomly per slide."""

    def __init__(self, width: int, height: int, cache_dir: Path, seed: Optional[str] = None) -> None:
        import random

        self._width = width
        self._height = height
        self._cache_dir = Path(cache_dir)
        self._paths: Dict[str, Path] = {}
        self._rng = random.Random(seed)
        self._last_slot: Optional[str] = None

    def _path_for(self, slot: str) -> Path:
        if slot not in self._paths:
            self._paths[slot] = build_branding_overlay(
                self._width,
                self._height,
                self._cache_dir / f"branding_{slot}.png",
                watermark_slot=slot,
            )
        return self._paths[slot]

    def next_overlay(self) -> Path:
        """Pick a watermark slot at random (never the same slot twice in a row)."""
        choices: List[str] = [s for s in WATERMARK_SLOTS if s != self._last_slot]
        slot = self._rng.choice(choices)
        self._last_slot = slot
        return self._path_for(slot)

    def get_overlay(self, *args, **kwargs) -> Path:
        """Compatibility wrapper: retrieve next branding overlay for a slide."""
        return self.next_overlay()
