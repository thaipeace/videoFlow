"""Curiosity-driven YouTube thumbnail: bold hook (<= 8 words) + visible bulletin label.

Rendered with Pillow only. The result is a JPEG kept under YouTube's 2 MB thumbnail limit.
Includes:
- 7 Day Themes for Thumbnail Text Color (Video only - 16:9):
  Thứ Hai (#2E8B57), Thứ Ba (#C62828), Thứ Tư (#D4A72C), Thứ Năm (#C4C9D0),
  Thứ Sáu (#202A44), Thứ Bảy (#4169A1), Chủ Nhật (#F4C95D).
- Category Title Banner Palette:
  Bản Tin Thời Sự (#17365D), Bản Tin Công Nghệ (#087F8C), Bản Tin Chiến Sự (#9F2028),
  Bản Tin Bóng Đá (#176B3A), Tin Nóng & Độc Lạ (#663399), Tin Vui (#B85C00).
- High-impact viral sticker layout for Shorts (9:16).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from haizflow.pipeline.branding import LOGO_COLOR, LOGO_TEXT, _bold_font

logger = logging.getLogger(__name__)

VN_TZ = timezone(timedelta(hours=7))

MAX_THUMBNAIL_BYTES = 1_900_000
HOOK_FILL = (255, 221, 0)
HOOK_ACCENT_FILL = (255, 255, 255)
LABEL_FILL = (214, 30, 38)

# -----------------------------------------------------------------------------
# 1. 7 Day Themes for Thumbnail Text Color (Video Only - 16:9)
# -----------------------------------------------------------------------------
WEEKDAY_THEMES: Dict[int, Dict[str, Any]] = {
    0: {
        "name": "Thanh Mộc",
        "title": "Xanh ngọc",
        "hex": "#2E8B57",
        "rgb": (46, 139, 87),
        "desc": "Khởi đầu, sinh trưởng, những tin mới và xu hướng mới.",
    },
    1: {
        "name": "Xích Hỏa",
        "title": "Đỏ son",
        "hex": "#C62828",
        "rgb": (198, 40, 40),
        "desc": "Tin nóng, thời sự, sự kiện đáng chú ý.",
    },
    2: {
        "name": "Hoàng Thổ",
        "title": "Vàng đất",
        "hex": "#D4A72C",
        "rgb": (212, 167, 44),
        "desc": "Kinh tế, đời sống, những câu chuyện thiết thực.",
    },
    3: {
        "name": "Bạch Kim",
        "title": "Bạc trắng",
        "hex": "#C4C9D0",
        "rgb": (196, 201, 208),
        "desc": "Công nghệ, khoa học, khám phá và sáng tạo.",
    },
    4: {
        "name": "Huyền Thủy",
        "title": "Đen xanh đêm",
        "hex": "#202A44",
        "rgb": (32, 42, 68),
        "desc": "Bí ẩn, điều tra, hồ sơ và những chuyện chưa có lời giải.",
    },
    5: {
        "name": "Lam Ảnh",
        "title": "Xanh chàm",
        "hex": "#4169A1",
        "rgb": (65, 105, 161),
        "desc": "Game, phim ảnh, giải trí, thế giới giả tưởng.",
    },
    6: {
        "name": "Vàng nắng cà phê",
        "title": "Vàng nắng cà phê",
        "hex": "#F4C95D",
        "rgb": (244, 201, 93),
        "desc": "Ấm áp, thư thái, tích cực.",
    },
}

# -----------------------------------------------------------------------------
# 2. Category Title Banner / Bulletin Color Palette
# -----------------------------------------------------------------------------
CATEGORY_LABEL_PALETTE: Dict[str, Dict[str, Any]] = {
    "tin_moi": {
        "label": "TIN NÓNG",
        "hex": "#D61E26",
        "rgb": (214, 30, 38),
        "name": "Đỏ tươi",
        "desc": "Chữ trắng nền đỏ nổi bật như bản đầu tiên.",
    },
    "tin_nong": {
        "label": "TIN NÓNG",
        "hex": "#D61E26",
        "rgb": (214, 30, 38),
        "name": "Đỏ tươi",
        "desc": "Khẩn cấp, mạnh mẽ, kịch tính (chữ trắng nền đỏ).",
    },
    "world": {
        "label": "BẢN TIN THỜI SỰ",
        "hex": "#17365D",
        "rgb": (23, 54, 93),
        "name": "Xanh navy",
        "desc": "Nghiêm túc, đáng tin cậy, chuyên nghiệp.",
    },
    "tech": {
        "label": "BẢN TIN CÔNG NGHỆ",
        "hex": "#087F8C",
        "rgb": (8, 127, 140),
        "name": "Xanh teal",
        "desc": "Hiện đại, kỹ thuật số, đổi mới.",
    },
    "war": {
        "label": "BẢN TIN CHIẾN SỰ",
        "hex": "#9F2028",
        "rgb": (159, 32, 40),
        "name": "Đỏ sẫm",
        "desc": "Khẩn cấp, mạnh mẽ, dễ nhận diện. Không dùng đỏ neon.",
    },
    "sports": {
        "label": "BẢN TIN BÓNG ĐÁ",
        "hex": "#176B3A",
        "rgb": (23, 107, 58),
        "name": "Xanh sân cỏ",
        "desc": "Thể thao, năng lượng, cạnh tranh.",
    },
    "viral": {
        "label": "TIN NÓNG & ĐỘC LẠ",
        "hex": "#663399",
        "rgb": (102, 51, 153),
        "name": "Tím đậm",
        "desc": "Khác biệt, dí dỏm, hơi kỳ quặc.",
    },
    "hope": {
        "label": "TIN VUI",
        "hex": "#B85C00",
        "rgb": (184, 92, 0),
        "name": "Cam đất",
        "desc": "Ấm áp, tích cực, tạo cảm giác thân thiện.",
    },
}


def get_weekday_hook_color(target_date: Optional[datetime] = None) -> Tuple[int, int, int]:
    """Return the RGB text accent color for the specified date (default: today in Vietnam time UTC+7).

    Used for the primary hook line on standard 16:9 landscape videos.
    """
    dt = target_date or datetime.now(VN_TZ)
    weekday_idx = dt.weekday()
    theme = WEEKDAY_THEMES.get(weekday_idx, WEEKDAY_THEMES[0])
    return theme["rgb"]


def get_category_label_color(label: str = "", category: Optional[str] = None) -> Tuple[int, int, int]:
    """Return the RGB color for the category bulletin label bar according to the palette."""
    cat_key = (category or "").lower().strip()
    lbl_lower = (label or "").lower()

    if cat_key in CATEGORY_LABEL_PALETTE:
        return CATEGORY_LABEL_PALETTE[cat_key]["rgb"]

    if "tin mới" in lbl_lower or "tin_moi" in cat_key or "morning" in cat_key:
        return CATEGORY_LABEL_PALETTE["tin_moi"]["rgb"]
    if "tin nóng" in lbl_lower or "tin_nong" in cat_key or "evening" in cat_key:
        return CATEGORY_LABEL_PALETTE["tin_nong"]["rgb"]
    if "thời sự" in lbl_lower or "thế giới" in lbl_lower or "world" in lbl_lower:
        return CATEGORY_LABEL_PALETTE["world"]["rgb"]
    if "công nghệ" in lbl_lower or "tech" in lbl_lower or "ai" in lbl_lower:
        return CATEGORY_LABEL_PALETTE["tech"]["rgb"]
    if "chiến sự" in lbl_lower or "quân sự" in lbl_lower or "war" in lbl_lower:
        return CATEGORY_LABEL_PALETTE["war"]["rgb"]
    if "bóng đá" in lbl_lower or "thể thao" in lbl_lower or "sports" in lbl_lower:
        return CATEGORY_LABEL_PALETTE["sports"]["rgb"]
    if "độc lạ" in lbl_lower or "tin lạ" in lbl_lower or "viral" in lbl_lower:
        return CATEGORY_LABEL_PALETTE["viral"]["rgb"]
    if "vui" in lbl_lower or "hy vọng" in lbl_lower or "hope" in lbl_lower:
        return CATEGORY_LABEL_PALETTE["hope"]["rgb"]

    return CATEGORY_LABEL_PALETTE["tin_moi"]["rgb"]


def thumbnail_size(aspect_ratio: str) -> Tuple[int, int]:
    return (720, 1280) if aspect_ratio == "9:16" else (1280, 720)


def _cover_crop(image: Image.Image, size: Tuple[int, int]) -> Image.Image:
    width, height = size
    scale = max(width / image.width, height / image.height)
    resized = image.resize(
        (max(width, round(image.width * scale)), max(height, round(image.height * scale))),
        Image.LANCZOS,
    )
    left = (resized.width - width) // 2
    top = (resized.height - height) // 2
    return resized.crop((left, top, left + width, top + height))


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int, stroke: int = 0) -> List[str]:
    lines: List[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        left, _, right, _ = draw.textbbox((0, 0), candidate, font=font, stroke_width=stroke)
        if right - left <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _fit_hook_landscape(
    draw: ImageDraw.ImageDraw, text: str, max_width: int, max_height: int, max_lines: int, start_size: int
) -> Tuple[ImageFont.ImageFont, List[str], int, int]:
    size = start_size
    while size >= 28:
        font = _bold_font(size)
        stroke = max(3, round(size * 0.09))
        lines = _wrap(draw, text, font, max_width, stroke)
        line_h = round(size * 1.12)
        if len(lines) <= max_lines and line_h * len(lines) <= max_height:
            widest = max(draw.textbbox((0, 0), ln, font=font, stroke_width=stroke)[2] for ln in lines)
            if widest <= max_width:
                return font, lines, stroke, line_h
        size -= 4
    font = _bold_font(28)
    return font, _wrap(draw, text, font, max_width, 3)[:max_lines], 3, 32


def _fit_hook_portrait(
    draw: ImageDraw.ImageDraw, text: str, max_width: int, max_height: int, max_lines: int = 3, start_size: int = 62
) -> Tuple[ImageFont.ImageFont, List[str], int]:
    size = start_size
    while size >= 32:
        font = _bold_font(size)
        lines = _wrap(draw, text, font, max_width)
        line_h = round(size * 1.22)
        if len(lines) <= max_lines and (line_h * len(lines)) <= max_height:
            widest = max((draw.textbbox((0, 0), ln, font=font)[2] - draw.textbbox((0, 0), ln, font=font)[0]) for ln in lines)
            if widest <= max_width:
                return font, lines, line_h
        size -= 4
    font = _bold_font(32)
    lines = _wrap(draw, text, font, max_width)[:max_lines]
    return font, lines, round(32 * 1.22)


def _format_category_badge_text(label: str) -> str:
    clean = (label or "").strip().upper()
    if not clean:
        return "BẢN TIN THỜI SỰ"
    if "ĐỘC LẠ" in clean or "TIN LẠ" in clean or "VIRAL" in clean:
        return "TIN NÓNG & ĐỘC LẠ"
    if "VUI" in clean or "HY VỌNG" in clean or "HOPE" in clean:
        return "TIN VUI THẾ GIỚI"
    if "CHIẾN" in clean or "QUÂN SỰ" in clean or "WAR" in clean:
        return "CHIẾN SỰ NÓNG"
    if "CÔNG NGHỆ" in clean or "TECH" in clean:
        return "CÔNG NGHỆ & ĐỘT PHÁ"
    if "BÓNG ĐÁ" in clean or "THỂ THAO" in clean or "SPORTS" in clean:
        return "BÓNG ĐÁ QUỐC TẾ"
    return clean


def _render_portrait_shorts_thumbnail(
    source_image: Optional[str],
    hook: str,
    label: str,
    output_path: Path,
    category: Optional[str] = None,
    include_logo: bool = True,
) -> Path:
    """Render a striking, viral YouTube Shorts (9:16) thumbnail.

    Features:
    - Upper-Middle safe zone positioning (18% - 44%), completely clear from
      YouTube Shorts bottom metadata (title, sound, subscribe button) and right-side icons.
    - Centered high-contrast 3D sticker boxes (Electric Yellow & Jet Black) for instant curiosity.
    - Category capsule badge with drop shadow, crisp outline, and thematic category color.
    - Enhanced vibrant photo grading (+25% saturation, +15% contrast, +30% sharpness)
      with soft cinematic edge vignettes that leave the central visual subject crystal clear.
    """
    size = (720, 1280)
    width, height = size
    base = min(width, height)

    background: Optional[Image.Image] = None
    if source_image and Path(source_image).is_file():
        try:
            with Image.open(source_image) as src:
                background = _cover_crop(src.convert("RGB"), size)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Shorts thumbnail source image unreadable (%s): %s", source_image, exc)

    if background is None:
        # Create dramatic deep cinematic gradient with a central spotlight
        background = Image.new("RGB", size, (14, 18, 30))
        bg_draw = ImageDraw.Draw(background)
        for r in range(400, 0, -10):
            alpha_ratio = (400 - r) / 400
            color = (
                round(14 + 50 * alpha_ratio),
                round(18 + 25 * alpha_ratio),
                round(30 + 75 * alpha_ratio),
            )
            bg_draw.ellipse((width // 2 - r, height // 2 - r, width // 2 + r, height // 2 + r), fill=color)

    # 1. Image Enhancement: punchier color, contrast and sharpness
    try:
        background = ImageEnhance.Color(background).enhance(1.25)
        background = ImageEnhance.Contrast(background).enhance(1.15)
        background = ImageEnhance.Sharpness(background).enhance(1.30)
    except Exception:
        pass

    canvas = background.convert("RGBA")

    # 2. Cinematic soft vignette: subtle top (0-16%) and bottom (82-100%)
    # Leaving the entire middle subject area (16% - 82%) bright, vibrant and crystal clear!
    vignette = Image.new("RGBA", size, (0, 0, 0, 0))
    v_px = vignette.load()
    for y in range(height):
        top_factor = max(0.0, (1 - y / (height * 0.16))) if y < height * 0.16 else 0.0
        bottom_factor = max(0.0, (y - height * 0.82) / (height * 0.18)) if y > height * 0.82 else 0.0
        alpha = round(160 * top_factor + 175 * bottom_factor)
        if alpha > 0:
            for x in range(width):
                v_px[x, y] = (0, 0, 0, alpha)
    canvas = Image.alpha_composite(canvas, vignette)

    draw = ImageDraw.Draw(canvas)

    # 3. Channel Branding Badge (Top-Left)
    if include_logo:
        badge_font = _bold_font(round(base * 0.040))
        bl, bt, br, bb = draw.textbbox((0, 0), LOGO_TEXT, font=badge_font)
        pad_bx = round(base * 0.024)
        pad_by = round(base * 0.012)
        badge_x = round(base * 0.055)
        badge_y = round(base * 0.045)
        draw.rounded_rectangle(
            (badge_x, badge_y, badge_x + (br - bl) + pad_bx * 2, badge_y + (bb - bt) + pad_by * 2),
            radius=round(base * 0.014),
            fill=(220, 20, 40, 240),
        )
        draw.text((badge_x + pad_bx - bl, badge_y + pad_by - bt), LOGO_TEXT, font=badge_font, fill=(255, 255, 255, 255))

    # 4. Text Zone: Upper-Middle Safe Area (y: 18% to 44%)
    # Centered horizontally, far above YouTube Shorts title/avatar/sound bar!
    hook_text = (hook or "").strip().upper()
    max_text_w = round(width * 0.86)
    max_hook_h = round(height * 0.28)
    font, lines, line_h = _fit_hook_portrait(draw, hook_text or "TIN NÓNG THẾ GIỚI", max_text_w, max_hook_h, max_lines=3, start_size=60)

    # Category Pill Badge (Centered) with category palette color
    badge_title = _format_category_badge_text(label)
    cat_color = get_category_label_color(label, category)
    cat_font = _bold_font(round(base * 0.038))
    cl, ct, cr, cb = draw.textbbox((0, 0), badge_title, font=cat_font)
    cat_pad_x = round(base * 0.045)
    cat_pad_y = round(base * 0.018)
    cat_w = (cr - cl) + cat_pad_x * 2
    cat_h = (cb - ct) + cat_pad_y * 2
    cat_x = (width - cat_w) // 2

    # Measure line box dimensions
    line_boxes = []
    pad_x = round(base * 0.035)
    pad_y = round(base * 0.016)

    for ln in lines:
        tb = draw.textbbox((0, 0), ln, font=font)
        tw = tb[2] - tb[0]
        th = tb[3] - tb[1]
        bw = tw + pad_x * 2
        bh = th + pad_y * 2
        line_boxes.append((ln, tw, th, bw, bh, tb))

    gap_lines = round(base * 0.016)
    total_hook_h = sum(b[4] for b in line_boxes) + gap_lines * (len(line_boxes) - 1)
    gap_cat_hook = round(base * 0.024)
    total_block_h = cat_h + gap_cat_hook + total_hook_h

    # Target Y center at ~25% of screen height
    start_y = max(round(height * 0.14), round(height * 0.25 - total_block_h * 0.45))

    # Draw Category Pill Badge
    cat_y = start_y
    # Shadow for pill
    draw.rounded_rectangle(
        (cat_x + 3, cat_y + 4, cat_x + cat_w + 3, cat_y + cat_h + 4),
        radius=round(cat_h / 2),
        fill=(0, 0, 0, 160),
    )
    # Pill background with category palette color
    draw.rounded_rectangle(
        (cat_x, cat_y, cat_x + cat_w, cat_y + cat_h),
        radius=round(cat_h / 2),
        fill=cat_color + (245,),
        outline=(255, 255, 255, 210),
        width=2,
    )
    draw.text(
        (cat_x + cat_pad_x - cl, cat_y + cat_pad_y - ct),
        badge_title,
        font=cat_font,
        fill=(255, 255, 255, 255),
    )

    # Draw Hook Sticker Boxes (Each line has its own rounded floating banner)
    cur_y = cat_y + cat_h + gap_cat_hook
    radius_box = round(base * 0.022)

    for idx, (ln, tw, th, bw, bh, tb) in enumerate(line_boxes):
        bx = (width - bw) // 2
        by = cur_y

        # Floating 3D Drop Shadow
        draw.rounded_rectangle(
            (bx + 4, by + 6, bx + bw + 4, by + bh + 6),
            radius=radius_box,
            fill=(0, 0, 0, 180),
        )

        # Style colors:
        # Line 0: Vivid Electric Yellow box with Jet Black text
        # Line 1: Deep Jet Black box with Pure White text & Gold accent border
        # Line 2+: Crimson Red box with Pure White text
        if idx == 0:
            box_fill = (255, 222, 0, 255)
            text_fill = (10, 12, 16, 255)
            box_outline = (255, 245, 140, 255)
        elif idx == 1:
            box_fill = (14, 16, 24, 250)
            text_fill = (255, 255, 255, 255)
            box_outline = (255, 222, 0, 200)
        else:
            box_fill = (220, 20, 40, 250)
            text_fill = (255, 255, 255, 255)
            box_outline = (255, 255, 255, 180)

        # Draw banner box
        draw.rounded_rectangle(
            (bx, by, bx + bw, by + bh),
            radius=radius_box,
            fill=box_fill,
            outline=box_outline,
            width=2,
        )

        # Text inside box
        text_x = bx + (bw - tw) // 2 - tb[0]
        text_y = by + (bh - th) // 2 - tb[1]
        draw.text(
            (text_x, text_y),
            ln,
            font=font,
            fill=text_fill,
        )

        cur_y += bh + gap_lines

    # 5. Top & Bottom subtle studio accent neon bars (giving cinematic polish)
    accent_h = 4
    draw.rectangle((0, 0, width, accent_h), fill=(255, 222, 0, 230))
    draw.rectangle((0, height - accent_h, width, height), fill=(220, 20, 40, 230))

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rgb = canvas.convert("RGB")
    quality = 92
    while True:
        rgb.save(output_path, "JPEG", quality=quality, optimize=True)
        if output_path.stat().st_size <= MAX_THUMBNAIL_BYTES or quality <= 60:
            break
        quality -= 8
    return output_path


def _render_landscape_thumbnail(
    source_image: Optional[str],
    hook: str,
    label: str,
    output_path: Path,
    category: Optional[str] = None,
    target_date: Optional[datetime] = None,
    include_logo: bool = True,
) -> Path:
    """Render a crisp, high-impact landscape (16:9) YouTube thumbnail with 7-day theming."""
    size = (1280, 720)
    width, height = size
    base = min(width, height)

    background: Optional[Image.Image] = None
    if source_image and Path(source_image).is_file():
        try:
            with Image.open(source_image) as src:
                background = _cover_crop(src.convert("RGB"), size)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Thumbnail source image unreadable (%s): %s", source_image, exc)
    if background is None:
        background = Image.new("RGB", size, (18, 24, 44))

    # Enhance photo contrast, color and sharpness
    try:
        background = ImageEnhance.Color(background).enhance(1.2)
        background = ImageEnhance.Contrast(background).enhance(1.15)
        background = background.filter(ImageFilter.UnsharpMask(radius=2, percent=60, threshold=3))
    except Exception:
        pass

    canvas = background.convert("RGBA")

    # Dark gradient on the left text side (~62% width), leaving right side bright
    shade = Image.new("RGBA", size, (0, 0, 0, 0))
    shade_px = shade.load()
    for y in range(height):
        for x in range(width):
            t = 1 - (x / width)
            strength = max(0.0, min(1.0, (t - 0.15) / 0.85))
            shade_px[x, y] = (0, 0, 0, round(215 * strength))
    canvas = Image.alpha_composite(canvas, shade)
    draw = ImageDraw.Draw(canvas)

    margin = round(base * 0.055)

    # Small VCH badge, top-left.
    if include_logo:
        badge_font = _bold_font(round(base * 0.045))
        bl, bt, br, bb = draw.textbbox((0, 0), LOGO_TEXT, font=badge_font)
        pad = round(base * 0.016)
        draw.rounded_rectangle(
            (margin, margin, margin + (br - bl) + pad * 2, margin + (bb - bt) + pad * 2),
            radius=round(base * 0.012),
            fill=LOGO_COLOR + (255,),
        )
        draw.text((margin + pad - bl, margin + pad - bt), LOGO_TEXT, font=badge_font, fill=(255, 255, 255, 255))

    # Text zone: left ~62% for landscape
    text_w = round(width * 0.62) - margin
    hook_text = (hook or "").strip().upper()
    label_text = (label or "").strip().upper()
    if label_text in ("BẢN TIN MỚI", "TIN MỚI", "BẢN TIN NÓNG") or (
        not label_text and (category or "").lower().strip() in ("tin_moi", "tin_nong")
    ):
        label_text = "TIN NÓNG"

    label_font = _bold_font(round(base * 0.062))
    ll, lt, lr, lb = draw.textbbox((0, 0), label_text or " ", font=label_font)
    label_h = (lb - lt) + round(base * 0.04)
    label_w = (lr - ll) + round(base * 0.06)

    zone_top = round(height * 0.34)
    zone_bottom = height - margin - round(height * 0.05)
    gap = round(base * 0.03)
    hook_area_h = zone_bottom - zone_top - label_h - gap
    max_lines = 3
    start = round(base * 0.2)
    font, lines, stroke, line_h = _fit_hook_landscape(draw, hook_text or " ", text_w, hook_area_h, max_lines, start)

    block_h = label_h + gap + line_h * len(lines)
    y = zone_bottom - block_h

    # 1. Label bar with Category Palette color
    label_color = get_category_label_color(label_text, category)
    if label_text:
        # Subtle 3D drop shadow behind label bar
        draw.rounded_rectangle(
            (margin + 3, y + 4, margin + label_w + 3, y + label_h + 4),
            radius=round(base * 0.012),
            fill=(0, 0, 0, 160),
        )
        draw.rounded_rectangle(
            (margin, y, margin + label_w, y + label_h),
            radius=round(base * 0.012),
            fill=label_color + (255,),
        )
        draw.text(
            (margin + (label_w - (lr - ll)) // 2 - ll, y + (label_h - (lb - lt)) // 2 - lt),
            label_text,
            font=label_font,
            fill=(255, 255, 255, 255),
        )
    y += label_h + gap

    # 2. 7-Day Themed Hook Text Color (Video only)
    # White accent line remains white; the primary line adapts to weekday theme color
    day_hook_color = get_weekday_hook_color(target_date)

    for idx, line in enumerate(lines):
        fill = day_hook_color if idx == 0 or len(lines) == 1 else HOOK_ACCENT_FILL
        stroke_color = (0, 0, 0, 255)

        # For Friday (#202A44 Huyền Thủy - deep night navy), provide a crisp bright stroke
        # so the dark text is perfectly legible on the dark gradient background
        if day_hook_color == (32, 42, 68) and fill == day_hook_color:
            stroke_color = (235, 240, 255, 255)

        draw.text(
            (margin, y + idx * line_h),
            line,
            font=font,
            fill=fill + (255,),
            stroke_width=stroke,
            stroke_fill=stroke_color,
        )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rgb = canvas.convert("RGB")
    quality = 92
    while True:
        rgb.save(output_path, "JPEG", quality=quality, optimize=True)
        if output_path.stat().st_size <= MAX_THUMBNAIL_BYTES or quality <= 60:
            break
        quality -= 8
    return output_path


def build_thumbnail(
    source_image: Optional[str],
    hook: str,
    label: str,
    output_path: Path,
    aspect_ratio: str = "16:9",
    category: Optional[str] = None,
    target_date: Optional[datetime] = None,
    include_logo: bool = True,
) -> Path:
    """Render a thumbnail JPEG and return its path.

    Automatically switches between:
    - High-impact viral sticker layout for vertical Shorts (9:16)
    - Clean broadcast layout for landscape videos (16:9) with 7-day theming
    """
    if aspect_ratio == "9:16":
        return _render_portrait_shorts_thumbnail(
            source_image=source_image,
            hook=hook,
            label=label,
            output_path=output_path,
            category=category,
            include_logo=include_logo,
        )
    return _render_landscape_thumbnail(
        source_image=source_image,
        hook=hook,
        label=label,
        output_path=output_path,
        category=category,
        target_date=target_date,
        include_logo=include_logo,
    )


