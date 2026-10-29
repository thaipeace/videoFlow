"""YouTube subscribe and bell ring call-to-action (CTA) animation with synchronized sound effects.

Generates a floating channel pill with an avatar, channel name, subscribe button,
interactive bell icon, mouse cursor animation, and synchronized click/bell SFX.
Designed for both 16:9 landscape and 9:16 portrait.
"""

from __future__ import annotations

import logging
import math
import subprocess
import wave
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw

from haizflow.config import RUNTIME_DATA_DIR
from haizflow.pipeline.branding import _bold_font
from haizflow.pipeline.slide_composer import _binary

logger = logging.getLogger(__name__)

CTA_DURATION_SECONDS = 3.0
CLICK_SUBSCRIBE_TIME = 0.8
CLICK_BELL_TIME = 1.45


def synthesize_cta_sfx(
    output_path: Path,
    click_time: float = CLICK_SUBSCRIBE_TIME,
    bell_time: float = CLICK_BELL_TIME,
    duration: float = CTA_DURATION_SECONDS,
) -> Path:
    """Synthesize high-fidelity mouse click and bell chime SFX."""
    sr = 48000
    total_samples = int(sr * duration)
    audio = np.zeros(total_samples, dtype=np.float32)

    # 1. Mouse Click at click_time (Subscribe button press: dual-click mechanical tactile pop)
    click_sample = int(click_time * sr)
    click_len = int(0.065 * sr)
    if click_sample + click_len <= total_samples:
        t_c = np.linspace(0, 0.065, click_len, endpoint=False)
        down_click = np.sin(2 * np.pi * 3400 * t_c) * np.exp(-t_c * 240) * 0.95
        body = np.sin(2 * np.pi * 1100 * t_c) * np.exp(-t_c * 120) * 0.70
        rel_start = int(0.025 * sr)
        t_rel = np.linspace(0, 0.040, click_len - rel_start, endpoint=False)
        release = np.sin(2 * np.pi * 2800 * t_rel) * np.exp(-t_rel * 200) * 0.55

        click_sound = down_click + body
        click_sound[rel_start:] += release
        audio[click_sample : click_sample + click_len] += click_sound * 1.5

    # 2. Bell Ding Chime at bell_time (Bright, punchy YouTube notification bell)
    bell_sample = int(bell_time * sr)
    bell_len = int(1.6 * sr)
    if bell_sample + bell_len > total_samples:
        bell_len = total_samples - bell_sample
    if bell_len > 0:
        t_b = np.linspace(0, bell_len / sr, bell_len, endpoint=False)
        decay_fast = np.exp(-t_b * 7.5)
        decay_slow = np.exp(-t_b * 1.8)

        # Metallic mallet strike transient (first 30ms)
        strike_len = min(bell_len, int(0.030 * sr))
        t_str = np.linspace(0, 0.030, strike_len, endpoint=False)
        strike = np.sin(2 * np.pi * 5200 * t_str) * np.exp(-t_str * 180) * 0.65

        # Rich YouTube bell chime: C7 (2093 Hz) fundamental, E7 (2637 Hz), G7 (3135 Hz), C8 (4186 Hz) sparkle
        chime = (
            0.65 * np.sin(2 * np.pi * 2093.00 * t_b) * decay_slow          # C7 fundamental
            + 0.45 * np.sin(2 * np.pi * 2637.02 * t_b) * decay_slow        # E7 major third
            + 0.50 * np.sin(2 * np.pi * 3135.96 * t_b) * decay_fast        # G7 fifth
            + 0.35 * np.sin(2 * np.pi * 2098.50 * t_b) * decay_slow        # Acoustic beating shimmer
            + 0.40 * np.sin(2 * np.pi * 4186.01 * t_b) * decay_fast        # C8 brilliance
        ) * 1.6
        chime[:strike_len] += strike
        audio[bell_sample : bell_sample + bell_len] += chime

    peak = np.max(np.abs(audio))
    scaled = (audio / peak) * 15000.0 if peak > 0 else audio
    audio_i16 = scaled.astype(np.int16)

    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output_path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(audio_i16.tobytes())
    return output_path


def _draw_cursor(draw: ImageDraw.ImageDraw, x: int, y: int, clicked: bool = False, scale: float = 1.0) -> None:
    s = 24 * scale
    if clicked:
        x += 2
        y += 2
    points = [
        (x, y),
        (x, y + s * 1.0),
        (x + s * 0.28, y + s * 0.72),
        (x + s * 0.55, y + s * 1.15),
        (x + s * 0.75, y + s * 1.02),
        (x + s * 0.48, y + s * 0.60),
        (x + s * 0.85, y + s * 0.60),
    ]
    shadow_points = [(px + 2, py + 2) for px, py in points]
    draw.polygon(shadow_points, fill=(0, 0, 0, 90))
    draw.polygon(points, fill=(255, 255, 255, 255), outline=(20, 20, 20, 255), width=2)


def _draw_checkmark(draw: ImageDraw.ImageDraw, cx: int, cy: int, size: int, fill: Tuple[int, int, int, int]) -> None:
    w = size * 0.5
    h = size * 0.4
    p1 = (cx - w * 0.6, cy)
    p2 = (cx - w * 0.1, cy + h * 0.6)
    p3 = (cx + w * 0.7, cy - h * 0.7)
    draw.line([p1, p2, p3], fill=fill, width=max(2, round(size * 0.16)), joint="curve")


def _draw_bell(
    draw: ImageDraw.ImageDraw,
    cx: int,
    cy: int,
    size: int,
    ringing: bool = False,
    ring_phase: float = 0.0,
    active: bool = False,
    alpha: float = 1.0,
) -> None:
    a_clamped = max(0.0, min(1.0, alpha))
    if a_clamped <= 0.005:
        return
    a_int = int(255 * a_clamped)
    fill_col = (255, 193, 7, a_int) if active else (40, 40, 40, a_int)
    outline_col = (20, 20, 20, a_int)
    angle = math.sin(ring_phase * 2 * math.pi) * 0.28 if ringing else 0.0

    w = size * 0.48
    h = size * 0.55
    top_y = -h * 0.55
    bottom_y = h * 0.35

    pts = [
        (0, top_y - 4),
        (-w * 0.25, top_y + 4),
        (-w * 0.38, 0),
        (-w * 0.60, bottom_y),
        (w * 0.60, bottom_y),
        (w * 0.38, 0),
        (w * 0.25, top_y + 4),
    ]

    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    rot_pts = []
    pivot_y = top_y
    for px, py in pts:
        rx = px * cos_a - (py - pivot_y) * sin_a
        ry = px * sin_a + (py - pivot_y) * cos_a + pivot_y
        rot_pts.append((cx + rx, cy + ry))

    draw.polygon(rot_pts, fill=fill_col, outline=outline_col, width=2)
    clapper_y = cy + bottom_y + 4
    draw.ellipse((cx - 4, clapper_y - 4, cx + 4, clapper_y + 4), fill=fill_col, outline=outline_col, width=1)

    if ringing:
        wave_alpha = int(180 * max(0.0, math.cos(ring_phase * 2 * math.pi)) * a_clamped)
        if wave_alpha > 0:
            draw.arc(
                (cx - w * 1.1, cy - h * 0.4, cx - w * 0.5, cy + h * 0.4),
                start=130,
                end=230,
                fill=(255, 193, 7, wave_alpha),
                width=3,
            )
            draw.arc(
                (cx + w * 0.5, cy - h * 0.4, cx + w * 1.1, cy + h * 0.4),
                start=310,
                end=410,
                fill=(255, 193, 7, wave_alpha),
                width=3,
            )


def render_cta_frame(
    t: float,
    total_dur: float = CTA_DURATION_SECONDS,
    width: int = 1920,
    height: int = 1080,
) -> Image.Image:
    """Render a single transparent frame of the subscribe CTA animation at time t."""
    frame = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    portrait = height > width

    card_alpha = 1.0
    if t < 0.35:
        card_alpha = max(0.0, t / 0.35)
    elif t > (total_dur - 0.55):
        card_alpha = max(0.0, (total_dur - t - 0.15) / 0.40)

    if card_alpha <= 0.005:
        return frame

    base = min(width, height)
    card_w = int(base * 0.84) if portrait else 820
    card_h = int(card_w * 0.17) if not portrait else int(card_w * 0.19)
    card_x = (width - card_w) // 2
    # Place card safely above the news ticker
    card_y = height - int(height * 0.22) if portrait else height - int(card_h * 2.2)

    if t < 0.35:
        card_y += int((1.0 - (t / 0.35)) * 40)

    card_img = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
    draw_c = ImageDraw.Draw(card_img)

    radius = int(card_h * 0.42)
    draw_c.rounded_rectangle(
        (0, 0, card_w, card_h),
        radius=radius,
        fill=(250, 250, 252, int(245 * card_alpha)),
        outline=(220, 222, 230, int(200 * card_alpha)),
        width=2,
    )

    # 1. Channel Avatar Badge
    pad = int(card_h * 0.15)
    av_size = card_h - pad * 2
    av_x = pad
    av_y = pad
    draw_c.ellipse((av_x, av_y, av_x + av_size, av_y + av_size), fill=(214, 30, 38, int(255 * card_alpha)))
    av_font = _bold_font(int(av_size * 0.36))
    bl, bt, br, bb = draw_c.textbbox((0, 0), "VCH", font=av_font)
    draw_c.text(
        (av_x + (av_size - (br - bl)) // 2 - bl, av_y + (av_size - (bb - bt)) // 2 - bt),
        "VCH",
        font=av_font,
        fill=(255, 255, 255, int(255 * card_alpha)),
    )

    # 2. Channel Names
    title_font = _bold_font(int(card_h * 0.28))
    sub_font = _bold_font(int(card_h * 0.17))
    tx = av_x + av_size + int(pad * 0.8)
    ty = int(card_h * 0.22)
    draw_c.text((tx, ty), "VẠN CHUYỆN", font=title_font, fill=(18, 20, 24, int(255 * card_alpha)))
    draw_c.text(
        (tx, ty + int(card_h * 0.34)),
        "@vanchuyen-102",
        font=sub_font,
        fill=(100, 105, 115, int(255 * card_alpha)),
    )

    # 3. Subscribe Button & Bell
    subscribed = t >= CLICK_SUBSCRIBE_TIME
    btn_clicked = CLICK_SUBSCRIBE_TIME <= t < (CLICK_SUBSCRIBE_TIME + 0.15)
    btn_w = int(card_w * 0.27)
    btn_h = int(card_h * 0.62)
    btn_r = int(btn_h * 0.5)

    bell_size = int(card_h * 0.60)
    bell_x = card_w - pad - bell_size // 2 - 12
    bell_y = card_h // 2

    btn_x = bell_x - bell_size // 2 - int(pad * 0.6) - btn_w
    btn_y = (card_h - btn_h) // 2

    btn_fill = (45, 48, 55, int(255 * card_alpha)) if subscribed else (214, 30, 38, int(255 * card_alpha))
    btn_font = _bold_font(int(btn_h * 0.34))

    if btn_clicked:
        draw_c.rounded_rectangle(
            (btn_x + 2, btn_y + 2, btn_x + btn_w - 2, btn_y + btn_h - 2),
            radius=btn_r - 2,
            fill=btn_fill,
        )
    else:
        draw_c.rounded_rectangle((btn_x, btn_y, btn_x + btn_w, btn_y + btn_h), radius=btn_r, fill=btn_fill)

    btn_text = "ĐÃ ĐĂNG KÝ" if subscribed else "ĐĂNG KÝ"
    tl, tt, tr, tb = draw_c.textbbox((0, 0), btn_text, font=btn_font)

    if subscribed:
        # Draw checkmark before text
        check_w = int(btn_h * 0.32)
        total_content_w = check_w + 6 + (tr - tl)
        start_content_x = btn_x + (btn_w - total_content_w) // 2
        _draw_checkmark(
            draw_c,
            start_content_x + check_w // 2,
            btn_y + btn_h // 2,
            check_w,
            fill=(255, 255, 255, int(255 * card_alpha)),
        )
        draw_c.text(
            (start_content_x + check_w + 6 - tl, btn_y + (btn_h - (tb - tt)) // 2 - tt),
            btn_text,
            font=btn_font,
            fill=(255, 255, 255, int(255 * card_alpha)),
        )
    else:
        draw_c.text(
            (btn_x + (btn_w - (tr - tl)) // 2 - tl, btn_y + (btn_h - (tb - tt)) // 2 - tt),
            btn_text,
            font=btn_font,
            fill=(255, 255, 255, int(255 * card_alpha)),
        )

    # 4. Bell
    bell_active = t >= CLICK_BELL_TIME
    bell_ringing = CLICK_BELL_TIME <= t < (CLICK_BELL_TIME + 1.0)
    ring_phase = (t - CLICK_BELL_TIME) * 4.5
    _draw_bell(
        draw_c,
        bell_x,
        bell_y,
        bell_size,
        ringing=bell_ringing,
        ring_phase=ring_phase,
        active=bell_active,
        alpha=card_alpha,
    )

    frame.paste(card_img, (card_x, card_y), card_img)

    # 5. Cursor Motion
    sub_center = (card_x + btn_x + btn_w // 2, card_y + btn_y + btn_h // 2)
    bell_center = (card_x + bell_x, card_y + bell_y)
    start_pos = (card_x + card_w + 30, card_y + card_h + 80)

    cur_x, cur_y = start_pos
    cur_clicked = False
    cur_visible = True

    def smoothstep(e0: float, e1: float, x: float) -> float:
        x = max(0.0, min(1.0, (x - e0) / (e1 - e0)))
        return x * x * (3 - 2 * x)

    if t < 0.3:
        cur_visible = False
    elif 0.3 <= t < (CLICK_SUBSCRIBE_TIME - 0.05):
        p = smoothstep(0.3, CLICK_SUBSCRIBE_TIME - 0.05, t)
        cur_x = int(start_pos[0] + (sub_center[0] - start_pos[0]) * p)
        cur_y = int(start_pos[1] + (sub_center[1] - start_pos[1]) * p)
    elif (CLICK_SUBSCRIBE_TIME - 0.05) <= t < (CLICK_SUBSCRIBE_TIME + 0.15):
        cur_x, cur_y = sub_center
        cur_clicked = CLICK_SUBSCRIBE_TIME <= t < (CLICK_SUBSCRIBE_TIME + 0.15)
    elif (CLICK_SUBSCRIBE_TIME + 0.15) <= t < (CLICK_BELL_TIME - 0.05):
        p = smoothstep(CLICK_SUBSCRIBE_TIME + 0.15, CLICK_BELL_TIME - 0.05, t)
        cur_x = int(sub_center[0] + (bell_center[0] - sub_center[0]) * p)
        cur_y = int(sub_center[1] + (bell_center[1] - sub_center[1]) * p)
    elif (CLICK_BELL_TIME - 0.05) <= t < (CLICK_BELL_TIME + 0.15):
        cur_x, cur_y = bell_center
        cur_clicked = CLICK_BELL_TIME <= t < (CLICK_BELL_TIME + 0.15)
    elif (CLICK_BELL_TIME + 0.15) <= t < min(2.35, total_dur - 0.55):
        p = smoothstep(CLICK_BELL_TIME + 0.15, min(2.35, total_dur - 0.55), t)
        cur_x = int(bell_center[0] + 60 * p)
        cur_y = int(bell_center[1] + 90 * p)
    else:
        cur_visible = False

    if cur_visible:
        draw_main = ImageDraw.Draw(frame)
        _draw_cursor(draw_main, cur_x, cur_y, clicked=cur_clicked)

    return frame


def render_subscribe_cta_video(
    output_mov_path: Path,
    width: int = 1920,
    height: int = 1080,
    fps: int = 30,
) -> Path:
    """Render a transparent RGBA MOV video of the subscribe animation."""
    output_mov_path = Path(output_mov_path).resolve()
    output_mov_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        _binary("ffmpeg"),
        "-y",
        "-f",
        "image2pipe",
        "-vcodec",
        "png",
        "-r",
        str(fps),
        "-i",
        "-",
        "-c:v",
        "png",
        str(output_mov_path),
    ]

    total_frames = int(CTA_DURATION_SECONDS * fps)
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )

    for i in range(total_frames):
        t = i / float(fps)
        img = render_cta_frame(t, CTA_DURATION_SECONDS, width, height)
        img.save(proc.stdin, "PNG")

    proc.stdin.close()
    proc.wait()

    if proc.returncode != 0:
        err = proc.stderr.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"CTA animation render failed: {err}")

    return output_mov_path


def get_or_build_subscribe_cta(
    width: int,
    height: int,
    staging_dir: Optional[Path] = None,
) -> Tuple[Path, Path]:
    """Acquire or synthesize the subscribe CTA animation video and SFX audio.

    Returns:
        (cta_video_path, cta_sfx_path)
    """
    ar_name = "9x16" if height > width else "16x9"
    cache_dir = Path(RUNTIME_DATA_DIR) / "cta_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    video_path = cache_dir / f"subscribe_cta_v2_{ar_name}.mov"
    sfx_path = cache_dir / "subscribe_cta_sfx_v2.wav"

    if not sfx_path.is_file() or sfx_path.stat().st_size < 1000:
        synthesize_cta_sfx(sfx_path)

    if not video_path.is_file() or video_path.stat().st_size < 1000:
        render_subscribe_cta_video(video_path, width=width, height=height)

    return video_path, sfx_path


def mix_cta_sfx_into_audio(
    scene_audio_path: Path,
    sfx_path: Path,
    delay_sec: float,
    output_path: Path,
) -> Path:
    """Mix the subscribe click and bell chimes into a scene's audio track at delay_sec."""
    scene_audio_path = Path(scene_audio_path).resolve()
    sfx_path = Path(sfx_path).resolve()
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    delay_ms = max(0, int(delay_sec * 1000))
    filter_expr = (
        f"[1:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,adelay={delay_ms}|{delay_ms},volume=0.45[sfx];"
        f"[0:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[vox];"
        f"[vox][sfx]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[mixed]"
    )

    cmd = [
        _binary("ffmpeg"),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(scene_audio_path),
        "-i",
        str(sfx_path),
        "-filter_complex",
        filter_expr,
        "-map",
        "[mixed]",
        "-c:a",
        "pcm_s16le",
        str(output_path),
    ]

    res = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if res.returncode != 0:
        logger.warning("Could not mix CTA SFX into scene audio: %s", res.stderr.strip())
        return scene_audio_path

    return output_path
