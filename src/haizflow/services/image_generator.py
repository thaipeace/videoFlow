"""Image Generation Service: Connects to Imagen 3, manages SHA-256 caching, and handles custom image imports."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import shutil
import tempfile
import threading
import time
from io import BytesIO
from pathlib import Path
from threading import Event
from typing import Callable, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from PIL import Image, ImageDraw

from haizflow.core.paths import cache_dir, runtime_data_dir
from haizflow.schemas.article_video import (
    ArticleProjectConfig,
    ArticleScene,
    AspectRatio,
)
from haizflow.services.secure_credentials import read_secret

logger = logging.getLogger(__name__)

IMAGEN_MODEL = "imagen-3.0-generate-002"
IMAGEN_ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{IMAGEN_MODEL}:predict"
CREDENTIAL_TARGET = "HaizFlow/Gemini/APIKey"
CREDENTIAL_POLLEN_TARGET = "HaizFlow/Pollinations/APIKey"

_LAST_FREE_AI_REQUEST_TIME: float = 0.0
_FREE_AI_LOCK = threading.Lock()


def _free_ai_cooldown_file() -> Path:
    d = runtime_data_dir() / "ai_pacing"
    d.mkdir(parents=True, exist_ok=True)
    return d / "free_ai_last_request.json"


def _get_last_free_ai_time() -> float:
    global _LAST_FREE_AI_REQUEST_TIME
    path = _free_ai_cooldown_file()
    if path.is_file():
        try:
            val = float(path.read_text(encoding="utf-8").strip())
            if val > _LAST_FREE_AI_REQUEST_TIME:
                _LAST_FREE_AI_REQUEST_TIME = val
        except Exception:
            pass
    return _LAST_FREE_AI_REQUEST_TIME


def _set_last_free_ai_time(timestamp: float) -> None:
    global _LAST_FREE_AI_REQUEST_TIME
    _LAST_FREE_AI_REQUEST_TIME = timestamp
    try:
        path = _free_ai_cooldown_file()
        path.write_text(str(timestamp), encoding="utf-8")
    except Exception:
        pass


SUPPORTED_IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".bmp"})


def get_effective_pollen_key(explicit_key: Optional[str] = None) -> str:
    """Retrieve Pollen / Pollinations API key from parameter, env, or secure vault."""
    if explicit_key and str(explicit_key).strip():
        candidate = str(explicit_key).strip()
        if candidate != "example-pollen-key":
            return candidate
    env_key = os.environ.get("POLLEN_KEY", "").strip()
    if env_key and env_key != "example-pollen-key":
        return env_key
    try:
        raw = read_secret(CREDENTIAL_POLLEN_TARGET).strip()
        if raw and raw != "example-pollen-key":
            return raw
    except Exception:
        pass
    return ""


class ImageGenerationError(RuntimeError):
    """Raised when an image generation API call fails."""

    def __init__(self, message: str, status_code: int = 0, retryable: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


def default_image_cache_directory() -> Path:
    """Return the global cache directory for generated article illustrations."""
    directory = cache_dir() / "article_images"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def compute_image_cache_key(prompt: str, aspect_ratio: str, style: str) -> str:
    """Generate a deterministic SHA-256 fingerprint from prompt, aspect ratio, and style."""
    data = f"{prompt.strip()}::{aspect_ratio.strip()}::{style.strip()}".encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def get_cached_image(cache_key: str, cache_dir_path: Optional[Path] = None) -> Optional[Path]:
    """Retrieve an existing cached image if present and non-empty."""
    directory = cache_dir_path or default_image_cache_directory()
    for ext in (".jpg", ".png", ".webp"):
        candidate = directory / f"{cache_key}{ext}"
        if candidate.is_file() and candidate.stat().st_size > 512:
            return candidate
    return None


def save_image_to_cache(
    cache_key: str,
    image_bytes: bytes,
    extension: str = ".jpg",
    cache_dir_path: Optional[Path] = None,
) -> Path:
    """Atomically persist generated image bytes into the local cache."""
    directory = cache_dir_path or default_image_cache_directory()
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{cache_key}{extension}"

    handle, temp_name = tempfile.mkstemp(prefix=".img-cache-", suffix=extension, dir=directory)
    with os.fdopen(handle, "wb") as temp_file:
        temp_file.write(image_bytes)
        temp_file.flush()
        os.fsync(temp_file.fileno())

    os.replace(temp_name, target)
    return target


def get_effective_gemini_api_key(api_key: Optional[str] = None) -> str:
    """Resolve a valid, non-mock Google Gemini API key if configured."""
    if api_key is not None:
        candidate = str(api_key).strip()
        if candidate and candidate != "example-gemini-key":
            return candidate
        return ""
    try:
        from haizflow.services.gemini_translation import active_key
        key = active_key()
        if key and key.strip() and key.strip() != "example-gemini-key":
            return key.strip()
    except Exception:
        pass
    env_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if env_key and env_key != "example-gemini-key":
        return env_key
    raw = read_secret(CREDENTIAL_TARGET).strip()
    if raw and raw != "example-gemini-key":
        return raw
    return ""


def call_imagen_api(
    prompt: str,
    aspect_ratio: str = "16:9",
    api_key: Optional[str] = None,
    timeout_seconds: float = 30.0,
) -> bytes:
    """Call Google Imagen 3 predict endpoint and return raw decoded image bytes."""
    key = get_effective_gemini_api_key(api_key)
    if not key:
        raise ImageGenerationError("Chưa có Google API Key. Hãy cấu hình trong Cài đặt.", status_code=401)

    url = f"{IMAGEN_ENDPOINT}?{urlencode({'key': key})}"
    payload = {
        "instances": [{"prompt": prompt}],
        "parameters": {
            "sampleCount": 1,
            "aspectRatio": aspect_ratio if aspect_ratio in {"1:1", "3:4", "4:3", "9:16", "16:9"} else "16:9",
            "personGeneration": "ALLOW_ADULT",
            "safetySetting": "BLOCK_MEDIUM_AND_ABOVE",
        },
    }

    req = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(req, timeout=timeout_seconds) as response:
            result = json.loads(response.read().decode("utf-8"))

        predictions = result.get("predictions")
        if not predictions or not isinstance(predictions, list):
            raise ImageGenerationError("Google Imagen không trả về kết quả hình ảnh hợp lệ.")

        b64_data = predictions[0].get("bytesBase64Encoded")
        if not b64_data:
            raise ImageGenerationError("Dữ liệu hình ảnh trả về bị rỗng.")

        return base64.b64decode(b64_data)

    except HTTPError as exc:
        if exc.code == 429:
            raise ImageGenerationError("Hết hạn mức gọi API (HTTP 429). Hãy thử lại sau ít phút.", status_code=429, retryable=True) from None
        if exc.code in {401, 403}:
            raise ImageGenerationError(f"API Key không hợp lệ hoặc không có quyền dùng Imagen 3 (HTTP {exc.code}).", status_code=exc.code) from None
        raise ImageGenerationError(f"Google Imagen API thất bại (HTTP {exc.code}).", status_code=exc.code) from None
    except URLError as exc:
        raise ImageGenerationError("Không kết nối được đến máy chủ Google Imagen. Kiểm tra mạng rồi thử lại.", retryable=True) from exc
    except (json.JSONDecodeError, ValueError) as exc:
        raise ImageGenerationError(f"Phản hồi từ Imagen bị lỗi: {exc}") from exc


def _safe_progress(cb: Optional[Callable[[str], None]], message: str) -> None:
    if cb:
        try:
            cb(message)
        except Exception:
            pass


def call_free_ai_api(
    prompt: str,
    aspect_ratio: str = "16:9",
    seed: Optional[int] = None,
    timeout_seconds: float = 80.0,
    retry_if_rate_limited: bool = True,
    pollinations_key: Optional[str] = None,
    progress_callback: Optional[Callable[[str], None]] = None,
    cancel_event: Optional[Event] = None,
) -> bytes:
    """Generate image via free community AI endpoints with automatic 45s rate-limit pacing and retry."""
    key = get_effective_pollen_key(pollinations_key)

    clean = prompt.strip().replace("\n", " ")
    # Ensure purely Vietnamese visual harness is applied in every prompt
    if "vietnamese" not in clean.lower():
        clean = (
            f"{clean}, authentic Vietnamese people, authentic Vietnamese ethnicity, "
            f"authentic Vietnamese scenery and architecture, detailed background, strictly no text, no watermark"
        )

    short_prompt = clean[:500] if len(clean) > 500 else clean
    w, h = (768, 432) if aspect_ratio == "16:9" else (432, 768) if aspect_ratio == "9:16" else (512, 512)
    effective_seed = seed if seed is not None else (abs(hash(clean)) % 10000000)
    encoded = quote(short_prompt, safe="")
    url = f"https://image.pollinations.ai/prompt/{encoded}?width={w}&height={h}&nologo=true&seed={effective_seed}"
    if key:
        url += f"&key={key}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    if key:
        headers["Authorization"] = f"Bearer {key}"

    # Pacing: If no key, respect 46s spacing from previous request to prevent HTTP 402
    if not key:
        with _FREE_AI_LOCK:
            last_t = _get_last_free_ai_time()
            elapsed = time.time() - last_t
            if last_t > 0 and elapsed < 46.0:
                cooldown = int(46.0 - elapsed) + 1
                for s in range(cooldown, 0, -1):
                    if cancel_event and cancel_event.is_set():
                        raise RuntimeError("Tiến trình tạo ảnh đã bị hủy.")
                    _safe_progress(progress_callback, f"Cổng AI miễn phí đang giãn cách (còn {s}s)... Đang tự động xếp hàng...")
                    time.sleep(1.0)

    max_attempts = 4 if retry_if_rate_limited else 1
    for attempt in range(max_attempts):
        if cancel_event and cancel_event.is_set():
            raise RuntimeError("Tiến trình tạo ảnh đã bị hủy.")

        req = Request(url, headers=headers)
        try:
            with urlopen(req, timeout=timeout_seconds) as response:
                data = response.read()
                content_type = response.headers.get("Content-Type", "")
                if data and len(data) > 1000 and ("image" in content_type or data[:2] in (b"\xff\xd8", b"\x89P")):
                    _set_last_free_ai_time(time.time())
                    target_w, target_h = (1920, 1080) if aspect_ratio == "16:9" else (1080, 1920) if aspect_ratio == "9:16" else (1080, 1080)
                    try:
                        with Image.open(BytesIO(data)) as img:
                            img = img.convert("RGB")
                            cw, ch = img.size
                            # Cleanly crop bottom 6% to remove any community watermark logo before final resize
                            if ch > 100 and not key:
                                img = img.crop((0, 0, cw, int(ch * 0.94)))
                            resized = img.resize((target_w, target_h), Image.Resampling.LANCZOS)
                            buf = BytesIO()
                            resized.save(buf, format="JPEG", quality=92)
                            return buf.getvalue()
                    except Exception:
                        return data
        except HTTPError as exc:
            if exc.code == 402 and retry_if_rate_limited and attempt < max_attempts - 1:
                wait_sec = 46
                _set_last_free_ai_time(time.time())
                logger.info("Free AI rate limit hit. Waiting %ds to retry (attempt %d)...", wait_sec, attempt + 1)
                for s in range(wait_sec, 0, -1):
                    if cancel_event and cancel_event.is_set():
                        raise RuntimeError("Tiến trình tạo ảnh đã bị hủy.")
                    _safe_progress(progress_callback, f"Cổng AI miễn phí đang giãn cách (còn {s}s)... Đang tự động đợi để tạo ảnh...")
                    time.sleep(1.0)
                continue
            logger.info("Free AI HTTP error: %s", exc)
            if attempt < max_attempts - 1:
                time.sleep(3.0)
                continue
            break
        except Exception as exc:
            logger.info("Free AI image endpoint attempt %d failed: %s", attempt + 1, exc)
            if attempt < max_attempts - 1:
                _safe_progress(progress_callback, f"Đang thử kết nối lại máy chủ tạo ảnh (lần {attempt + 2})...")
                time.sleep(3.0)
                continue
            break

    raise ImageGenerationError("Không thể tạo ảnh từ cổng AI miễn phí (Cổng công cộng bận hoặc quá tải). Hãy thử lại sau ít giây hoặc nhập Pollen Key / Google Key.", retryable=True)


def call_local_sd_api(
    prompt: str,
    aspect_ratio: str = "16:9",
    base_url: str = "http://127.0.0.1:7860",
    timeout_seconds: float = 8.0,
) -> bytes:
    """Generate image using local Stable Diffusion WebUI / Forge if running."""
    w, h = (960, 540) if aspect_ratio == "16:9" else (540, 960) if aspect_ratio == "9:16" else (768, 768)
    url = f"{base_url.rstrip('/')}/sdapi/v1/txt2img"
    payload = {
        "prompt": prompt,
        "negative_prompt": "blurry, low quality, deformed, bad anatomy, text, watermark",
        "width": w,
        "height": h,
        "steps": 20,
    }
    req = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=timeout_seconds) as response:
            res = json.loads(response.read().decode("utf-8"))
            images = res.get("images", [])
            if images and isinstance(images[0], str):
                return base64.b64decode(images[0])
    except Exception:
        pass
    raise ImageGenerationError("Local Stable Diffusion không phản hồi.")


def create_fallback_placeholder_image(
    prompt: str,
    width: int = 1920,
    height: int = 1080,
    style: str = "cinematic",
    character_image_path: Optional[Path | str] = None,
    seed: Optional[int] = None,
) -> bytes:
    """Generate a high-quality, scene-aware illustration card with dynamic contextual visuals."""
    p_lower = prompt.lower()

    # Dynamic palette selection based on scene mood
    palette_options = [
        ((12, 16, 26), (28, 42, 62)),   # Midnight blue / medical
        ((18, 14, 24), (45, 30, 55)),   # Deep twilight
        ((14, 20, 22), (25, 48, 52)),   # Teal / clinical
        ((22, 16, 14), (55, 36, 28)),   # Warm amber / nostalgic
        ((16, 16, 20), (38, 40, 48)),   # Dark graphite / neutral
    ]
    seed_offset = seed if seed is not None else 0
    palette_idx = (abs(hash(prompt)) + seed_offset) % len(palette_options)
    color1, color2 = palette_options[palette_idx]

    img = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(img)

    # Vertical gradient background
    for y in range(height):
        ratio = y / height
        r = int(color1[0] + (color2[0] - color1[0]) * ratio)
        g = int(color1[1] + (color2[1] - color1[1]) * ratio)
        b = int(color1[2] + (color2[2] - color1[2]) * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    # Detect if scene is about an ECG / heart monitor / medical equipment
    is_ecg_scene = any(k in p_lower for k in ("machine", "monitor", "rhythm", "beep", "máy", "nhịp", "bíp", "flatline", "ecg"))
    is_char_scene = any(k in p_lower for k in ("my dung", "woman", "girl", "mother", "cô", "mẹ", "bà", "nằm", "quay đầu", "head", "body", "face", "ngực"))

    has_custom_visual = False

    if is_ecg_scene and not is_char_scene:
        # Render a sleek ECG / hospital telemetry monitor visualization
        grid_color = (color2[0] + 15, color2[1] + 25, color2[2] + 25)
        for x in range(int(width * 0.1), int(width * 0.9), 48):
            draw.line([(x, int(height * 0.18)), (x, int(height * 0.78))], fill=grid_color)
        for y in range(int(height * 0.18), int(height * 0.78), 48):
            draw.line([(int(width * 0.1), y), (int(width * 0.9), y)], fill=grid_color)

        # Pulse wave line
        pulse_points = []
        center_y = int(height * 0.48)
        start_x = int(width * 0.1)
        end_x = int(width * 0.9)
        step = 8
        for x in range(start_x, end_x, step):
            rel_x = (x - start_x) % 360
            if 100 <= rel_x <= 130:
                y = center_y - int((rel_x - 100) * 4)
            elif 130 < rel_x <= 160:
                y = center_y + int((rel_x - 130) * 3)
            elif 160 < rel_x <= 190:
                y = center_y - int((190 - rel_x) * 2)
            else:
                y = center_y
            pulse_points.append((x, y))

        draw.line(pulse_points, fill=(50, 240, 160), width=3)
        draw.rectangle([int(width * 0.1), int(height * 0.18), int(width * 0.9), int(height * 0.78)], outline=(50, 240, 160, 140), width=2)
        draw.text((int(width * 0.12), int(height * 0.22)), "ICU PATIENT MONITOR • VITAL SIGNS TELEMETRY", fill=(50, 240, 160))
        has_custom_visual = True

    elif character_image_path and is_char_scene:
        char_path = Path(character_image_path).resolve()
        if char_path.is_file():
            try:
                with Image.open(char_path) as char_img:
                    char_img = char_img.convert("RGB")
                    cw, ch = char_img.size

                    # Pick different pose angle if multi-view sheet
                    if cw / max(1, ch) > 1.35:
                        view_seed = abs(hash(prompt)) % 3
                        if view_seed == 0:
                            # 3/4 pose (center)
                            char_crop = char_img.crop((int(cw * 0.30), 0, int(cw * 0.70), ch))
                        elif view_seed == 1:
                            # Front or left pose
                            char_crop = char_img.crop((0, 0, int(cw * 0.38), ch))
                        else:
                            # Right or dramatic pose
                            char_crop = char_img.crop((int(cw * 0.62), 0, cw, ch))
                    else:
                        char_crop = char_img

                    # Position character portrait as a clean reference stamp on the right side
                    max_target_w = int(width * 0.30)
                    max_target_h = int(height * 0.62)
                    cc_w, cc_h = char_crop.size
                    scale = min(max_target_w / max(1, cc_w), max_target_h / max(1, cc_h))
                    fitted_w = max(1, int(cc_w * scale))
                    fitted_h = max(1, int(cc_h * scale))
                    resized_char = char_crop.resize((fitted_w, fitted_h), Image.Resampling.LANCZOS)

                    pos_x = int(width * 0.66)
                    pos_y = int(height * 0.16) + (max_target_h - fitted_h) // 2
                    img.paste(resized_char, (pos_x, pos_y))

                    # Stamp card border & header
                    draw.rectangle(
                        [pos_x - 3, pos_y - 3, pos_x + fitted_w + 3, pos_y + fitted_h + 3],
                        outline=(255, 255, 255, 140),
                        width=2,
                    )
                    draw.text((pos_x, pos_y - 20), "NHÂN VẬT TRỌNG TÂM", fill=(203, 213, 225))

                    # Storyboard situation description panel on the left side
                    sb_x1 = int(width * 0.06)
                    sb_y1 = int(height * 0.16)
                    sb_x2 = int(width * 0.62)
                    sb_y2 = int(height * 0.78)
                    draw.rectangle([sb_x1, sb_y1, sb_x2, sb_y2], fill=(12, 16, 24, 200), outline=(255, 255, 255, 100), width=2)
                    draw.text((sb_x1 + 24, sb_y1 + 24), "PHÂN CẢNH TRỌNG TÂM (STORYBOARD)", fill=(56, 189, 248))
                    draw.text((sb_x1 + 24, sb_y1 + 54), "[TÌNH HUỐNG & HÀNH ĐỘNG]", fill=(148, 163, 184))

                    # Word wrap snippet into the storyboard panel
                    words = prompt.split()
                    lines_to_draw = []
                    curr_line = ""
                    for word in words:
                        if len(curr_line) + len(word) + 1 < 42:
                            curr_line += (" " if curr_line else "") + word
                        else:
                            lines_to_draw.append(curr_line)
                            curr_line = word
                            if len(lines_to_draw) >= 6:
                                break
                    if curr_line and len(lines_to_draw) < 6:
                        lines_to_draw.append(curr_line)

                    line_y = sb_y1 + 90
                    for l in lines_to_draw:
                        draw.text((sb_x1 + 24, line_y), l, fill=(241, 245, 249))
                        line_y += 24

                    has_custom_visual = True
            except Exception as exc:
                logger.warning("Could not composite character sheet %s: %s", char_path, exc)

    if not has_custom_visual:
        # Draw a stylized artistic twilight landscape so it is NEVER an empty blank rectangle
        sun_x = int(width * 0.75)
        sun_y = int(height * 0.38)
        sun_r = int(height * 0.12)
        draw.ellipse([sun_x - sun_r, sun_y - sun_r, sun_x + sun_r, sun_y + sun_r], fill=(color2[0] + 60, color2[1] + 55, color2[2] + 40))

        # Distant misty mountains
        mountains_1 = [
            (0, int(height * 0.65)),
            (int(width * 0.22), int(height * 0.48)),
            (int(width * 0.48), int(height * 0.60)),
            (int(width * 0.78), int(height * 0.45)),
            (width, int(height * 0.58)),
            (width, height),
            (0, height),
        ]
        draw.polygon(mountains_1, fill=(color1[0] + 20, color1[1] + 24, color1[2] + 32))

        # Midground mountain ridges
        mountains_2 = [
            (0, int(height * 0.72)),
            (int(width * 0.32), int(height * 0.58)),
            (int(width * 0.64), int(height * 0.72)),
            (width, int(height * 0.64)),
            (width, height),
            (0, height),
        ]
        draw.polygon(mountains_2, fill=(color1[0] + 12, color1[1] + 14, color1[2] + 20))

        # Calm river / lake surface
        water_y = int(height * 0.80)
        draw.rectangle([0, water_y, width, height], fill=(color1[0] + 6, color1[1] + 8, color1[2] + 14))
        for wy in range(water_y + 16, height - 12, 18):
            draw.line([(int(width * 0.15), wy), (int(width * 0.85), wy)], fill=(color2[0] + 18, color2[1] + 24, color2[2] + 30))

    # Clean aesthetic vignette border without any raw prompt text or labels
    card_x1 = int(width * 0.06)
    card_y1 = int(height * 0.08)
    card_x2 = int(width * 0.94)
    card_y2 = int(height * 0.92)
    draw.rectangle([card_x1, card_y1, card_x2, card_y2], outline=(color2[0] + 30, color2[1] + 30, color2[2] + 30), width=2)

    buf = BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def import_custom_scene_image(
    source_path: Path | str,
    destination_path: Path,
    aspect_ratio: AspectRatio = "16:9",
) -> Path:
    """Validate, fit to target aspect ratio (center crop), and save a custom image."""
    src = Path(source_path).resolve()
    if not src.is_file():
        raise FileNotFoundError(f"Source image does not exist: {src}")

    if src.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
        raise ValueError(f"Unsupported image format: {src.suffix}. Must be one of {', '.join(SUPPORTED_IMAGE_EXTENSIONS)}")

    target_w, target_h = (1920, 1080) if aspect_ratio == "16:9" else (1080, 1920) if aspect_ratio == "9:16" else (1080, 1080)
    target_ratio = target_w / target_h

    destination_path.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(src) as img:
        img = img.convert("RGB")
        img_w, img_h = img.size
        img_ratio = img_w / img_h

        if abs(img_ratio - target_ratio) > 0.01:
            # Crop to fit target aspect ratio centrally
            if img_ratio > target_ratio:
                # Image is wider: crop sides
                new_w = int(img_h * target_ratio)
                offset_x = (img_w - new_w) // 2
                img = img.crop((offset_x, 0, offset_x + new_w, img_h))
            else:
                # Image is taller: crop top/bottom
                new_h = int(img_w / target_ratio)
                offset_y = (img_h - new_h) // 2
                img = img.crop((0, offset_y, img_w, offset_y + new_h))

        # High-quality resize
        img = img.resize((target_w, target_h), Image.Resampling.LANCZOS)
        img.save(destination_path, format="JPEG", quality=92, optimize=True)

    return destination_path


def _should_allow_free_online(allow_free_online: Optional[bool] = None) -> bool:
    """Determine whether external free community online calls are permitted."""
    if allow_free_online is False:
        return False
    if os.environ.get("HAIZFLOW_OFFLINE", "").lower() in ("1", "true"):
        return False
    if allow_free_online is True:
        return True
    # If not explicitly specified, auto-detect: avoid network in unittests
    import sys
    if "unittest" in sys.modules and any("test" in arg.lower() for arg in sys.argv) and not os.environ.get("HAIZFLOW_NETWORK_TESTS"):
        return False
    return True


def generate_scene_image(
    prompt: str,
    destination_path: Path,
    aspect_ratio: AspectRatio = "16:9",
    style: str = "cinematic",
    api_key: Optional[str] = None,
    use_cache: bool = True,
    cache_dir_path: Optional[Path] = None,
    character_image_path: Optional[Path | str] = None,
    allow_free_online: Optional[bool] = None,
    progress_callback: Optional[Callable[[str], None]] = None,
    cancel_event: Optional[Event] = None,
    seed: Optional[int] = None,
) -> Path:
    """Generate a single illustration image, checking cache first and cascading through engines."""
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    cache_key = compute_image_cache_key(prompt, aspect_ratio, style)

    # 1. Check cache
    if use_cache:
        cached = get_cached_image(cache_key, cache_dir_path)
        if cached:
            shutil.copy2(cached, destination_path)
            return destination_path

    # Ensure fresh seed when bypassing cache or regenerating
    if not use_cache and seed is None:
        import random
        seed = random.randint(100000, 99999999)

    image_bytes: Optional[bytes] = None
    last_error: Optional[str] = None

    # 2. Try Google Imagen 3 if valid API key is configured
    effective_key = get_effective_gemini_api_key(api_key)
    if effective_key:
        try:
            image_bytes = call_imagen_api(prompt=prompt, aspect_ratio=aspect_ratio, api_key=effective_key)
            logger.info("Generated image via Google Imagen 3.")
        except Exception as exc:
            last_error = str(exc)
            logger.warning("Imagen 3 generation failed: %s. Falling back to secondary engines.", exc)

    # 3. Try Local Stable Diffusion (Forge / WebUI on 127.0.0.1:7860)
    if image_bytes is None:
        try:
            image_bytes = call_local_sd_api(prompt=prompt, aspect_ratio=aspect_ratio, timeout_seconds=1.5)
            logger.info("Generated image via local Stable Diffusion WebUI.")
        except Exception:
            pass

    # 4. Try Free Online AI (Pollinations community endpoint with pacing)
    online_allowed = _should_allow_free_online(allow_free_online)
    if image_bytes is None and online_allowed:
        try:
            image_bytes = call_free_ai_api(
                prompt=prompt,
                aspect_ratio=aspect_ratio,
                seed=seed,
                timeout_seconds=80.0,
                progress_callback=progress_callback,
                cancel_event=cancel_event,
            )
            logger.info("Generated image via Free Online AI engine.")
        except Exception as exc:
            last_error = str(exc)
            logger.warning("Free Online AI engine failed: %s", exc)

    # 5. Handle failure: DO NOT silently generate empty/fallback images in online mode!
    if image_bytes is None:
        if online_allowed:
            raise ImageGenerationError(
                f"Không thể tạo ảnh do máy chủ AI đang bận hoặc quá tải ({last_error or 'Giới hạn tần suất 45s'}). "
                "Vui lòng bấm 'Tạo lại ảnh này' sau vài giây hoặc cấu hình Pollen Key.",
                retryable=True,
            )
        # Offline mode / unittest fallback:
        w, h = (1920, 1080) if aspect_ratio == "16:9" else (1080, 1920) if aspect_ratio == "9:16" else (1080, 1080)
        image_bytes = create_fallback_placeholder_image(
            prompt=prompt,
            width=w,
            height=h,
            style=style,
            character_image_path=character_image_path,
            seed=seed,
        )
        destination_path.write_bytes(image_bytes)
        return destination_path

    # 6. Save to cache ONLY for genuine AI-generated images
    if use_cache:
        save_image_to_cache(cache_key, image_bytes, cache_dir_path=cache_dir_path)

    # 7. Save to destination
    destination_path.write_bytes(image_bytes)
    return destination_path


def generate_scenes_images(
    scenes: List[ArticleScene],
    config: ArticleProjectConfig,
    output_dir: Path,
    progress_callback: Optional[Callable[[int, str], None]] = None,
    cancel_event: Optional[Event] = None,
    allow_free_online: Optional[bool] = None,
) -> List[ArticleScene]:
    """Process all scenes marked with has_image=True and populate their image_path."""
    output_dir.mkdir(parents=True, exist_ok=True)
    target_scenes = [s for s in scenes if s.has_image]
    total = len(target_scenes)

    if total == 0:
        return scenes

    api_key = get_effective_gemini_api_key()

    for i, scene in enumerate(target_scenes, start=1):
        if cancel_event and cancel_event.is_set():
            raise RuntimeError("Image generation cancelled by user.")

        pct = int((i / total) * 100)
        if progress_callback:
            progress_callback(pct, f"Đang tạo hình minh họa {i}/{total}...")

        def sub_progress_cb(detail_msg: str) -> None:
            if progress_callback:
                progress_callback(pct, detail_msg)

        dest_file = output_dir / f"scene_{scene.scene_index:03d}.jpg"
        prompt = scene.image_prompt if scene.image_prompt else scene.text

        # Resolve character reference sheet specifically for this scene's active character
        scene_char_sheet: Optional[Path] = None
        char_id = scene.character_id or config.character_id
        if char_id and char_id != "none":
            try:
                from haizflow.services.character_catalog import (
                    get_character_by_id,
                    resolve_character_avatar_path,
                )
                char_preset = get_character_by_id(char_id)
                if char_preset:
                    if char_preset.thumbnail:
                        resolved = resolve_character_avatar_path(char_preset.thumbnail)
                        if resolved.is_file():
                            scene_char_sheet = resolved
                    if not scene_char_sheet and char_preset.reference_images:
                        for ref in char_preset.reference_images:
                            resolved = resolve_character_avatar_path(ref)
                            if resolved.is_file():
                                scene_char_sheet = resolved
                                break
            except Exception as exc:
                logger.warning("Could not resolve character model sheet for %s: %s", char_id, exc)

        generate_scene_image(
            prompt=prompt,
            destination_path=dest_file,
            aspect_ratio=config.aspect_ratio,
            style=config.image_style,
            api_key=api_key,
            character_image_path=scene_char_sheet,
            allow_free_online=allow_free_online,
            progress_callback=sub_progress_cb,
            cancel_event=cancel_event,
        )
        scene.image_path = str(dest_file.resolve())

    return scenes
