#!/usr/bin/env python3
"""CI/Serverless Runner for HaizFlow / videoFlow Automated Daily News.

Designed for GitHub Actions, Docker, or Cloud Cron jobs:
1. Automatically determines the appropriate news category based on UTC time (or command-line argument).
2. Sets up credentials from environment variables (GEMINI_API_KEY, YOUTUBE_TOKEN_JSON, YOUTUBE_CLIENT_SECRET_JSON).
3. Invokes scripts/run_daily_news.py with proper parameters.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ci_daily_news")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT))

# Shorts Tin Độc Lạ (viral) is temporarily disabled until a better approach is found.
# Flip to True to re-enable (also re-add the cron + 'viral' option in daily_news.yml).
VIRAL_ENABLED = False

SCHEDULE_RULES = [
    # (name, utc_hour_range, min_topics, aspect_ratio)
    # 06:03 VN (UTC+7) = 23:03 UTC (ngày hôm trước) -> Tin Mới (Thế giới + Chiến sự + Thể thao 16:9)
    ("tin_moi", range(22, 24), 9, "16:9"),
    # 12:03 VN (UTC+7) = 05:03 UTC -> Shorts Tin Vui (9:16 <= 25s)
    ("hope", range(3, 8), 1, "9:16"),
    # 17:33 VN (UTC+7) = 10:33 UTC -> Shorts Tin AI Nổi Bật (9:16 <= 25s)
    ("ai", range(8, 22), 1, "9:16"),
]


def resolve_category_from_utc() -> tuple[str, str, int]:
    """Auto-detect category, aspect ratio, and topic count from current UTC time.

    Targets (UTC): tin_moi 23:03 (06:03 VN), hope 05:03 (12:03 VN), ai 10:33 (17:33 VN).
    The day is partitioned so that GitHub's cron start delays still resolve correctly.
    """
    now_utc = datetime.now(timezone.utc)
    hour = now_utc.hour
    minute = now_utc.minute
    total_minutes = hour * 60 + minute

    logger.info("Current UTC time: %02d:%02d (Hour %d)", hour, minute, hour)

    # Tin Mới: 22:00 - 03:00 UTC (target 23:03 UTC = 06:03 VN) -> Thế giới + Chiến sự + Thể thao (9 tin 16:9)
    if total_minutes >= 22 * 60 or total_minutes < 3 * 60:
        return "tin_moi", "16:9", 9

    # Short Tin Vui: 03:00 - 08:00 UTC (target 05:03 UTC = 12:03 VN) -> 1 tin vui <= 25s (9:16)
    if 3 * 60 <= total_minutes < 8 * 60:
        return "hope", "9:16", 1

    # Short Tin AI Nổi Bật: 08:00 - 22:00 UTC (target 10:33 UTC = 17:33 VN) -> 1 tin AI đột phá <= 25s (9:16)
    return "ai", "9:16", 1


def setup_ci_environment() -> None:
    """Prepare runtime/data directory and write credentials from environment variables."""
    runtime_data = PROJECT_ROOT / "runtime" / "data"
    runtime_data.mkdir(parents=True, exist_ok=True)

    # 1. YouTube OAuth Token
    token_env = os.environ.get("YOUTUBE_TOKEN_JSON", "").strip()
    token_file = runtime_data / "youtube_token.json"
    if token_env and not token_file.is_file():
        try:
            # Validate JSON
            parsed = json.loads(token_env)
            token_file.write_text(json.dumps(parsed, indent=2), encoding="utf-8")
            logger.info("Wrote youtube_token.json from YOUTUBE_TOKEN_JSON secret.")
        except Exception as exc:
            logger.warning("Could not write YOUTUBE_TOKEN_JSON: %s", exc)

    # 2. YouTube Client Secret
    secret_env = os.environ.get("YOUTUBE_CLIENT_SECRET_JSON", "").strip()
    secret_file = runtime_data / "youtube_client_secret.json"
    if secret_env and not secret_file.is_file():
        try:
            parsed = json.loads(secret_env)
            secret_file.write_text(json.dumps(parsed, indent=2), encoding="utf-8")
            logger.info("Wrote youtube_client_secret.json from YOUTUBE_CLIENT_SECRET_JSON secret.")
        except Exception as exc:
            logger.warning("Could not write YOUTUBE_CLIENT_SECRET_JSON: %s", exc)

    # 3. Daily News Settings file
    settings_file = runtime_data / "daily_news_settings.json"
    if not settings_file.is_file():
        default_settings = {
            "selected_category": "tin_moi",
            "max_topics": 8,
            "aspect_ratio": "16:9",
            "voice_id": "vi-VN-NamMinhNeural",
            "detail_level": "standard",
            "bgm_enabled": True,
            "bgm_volume": 0.08,
            "auto_upload_youtube": True,
            "youtube_privacy": "public",
            "auto_add_to_playlist": True,
            "youtube_playlist_tin_moi": "Bản tin thế giới",
            "youtube_playlist_hope": "Bản tin thế giới",
            "youtube_playlist_viral": "Bản tin thế giới",
            "youtube_playlist_tin_nong": "Bản tin thế giới",
            "schedule_time": "05:30",
            "schedule_wake_up": True,
        }
        settings_file.write_text(json.dumps(default_settings, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("Initialized default daily_news_settings.json.")

    has_token = bool(token_env) or token_file.is_file()
    has_secret = bool(secret_env) or secret_file.is_file()
    has_gemini = bool(os.environ.get("GEMINI_API_KEY", "").strip())
    logger.info("------------------------------------------------------------------")
    logger.info("CI Environment Credentials Check:")
    logger.info("  • GEMINI_API_KEY            : %s", "CONFIGURED" if has_gemini else "MISSING (Will use offline template fallback)")
    logger.info("  • YOUTUBE_TOKEN_JSON        : %s", "CONFIGURED" if has_token else "MISSING (Cannot upload to YouTube!)")
    logger.info("  • YOUTUBE_CLIENT_SECRET_JSON: %s", "CONFIGURED" if has_secret else "MISSING (Needed to refresh expired tokens)")
    logger.info("------------------------------------------------------------------")


def main() -> int:
    parser = argparse.ArgumentParser(description="HaizFlow CI / Cloud Runner for Daily News")
    parser.add_argument(
        "--category",
        choices=["auto", "tin_moi", "hope", "ai", "tin_nong", "viral"],
        default="auto",
        help="Category to produce. 'auto' calculates the category based on current UTC time.",
    )
    parser.add_argument("--aspect-ratio", choices=["16:9", "9:16"], default=None)
    parser.add_argument("--max-topics", type=int, default=None)
    parser.add_argument("--youtube", action="store_true", default=True, help="Upload to YouTube after generation.")
    parser.add_argument("--no-youtube", dest="youtube", action="store_false")
    parser.add_argument("--quick-test", action="store_true", help="Run fast dry-run with mock data.")
    args = parser.parse_args()

    setup_ci_environment()

    # Determine category, aspect ratio, and topic count
    if args.category == "auto":
        category, default_ar, default_topics = resolve_category_from_utc()
    else:
        category = args.category
        if category in ("hope", "viral", "ai"):
            default_ar, default_topics = "9:16", 1
        elif category == "tin_moi":
            default_ar, default_topics = "16:9", 9
        else:
            default_ar, default_topics = "16:9", 8

    if category == "viral" and not VIRAL_ENABLED:
        logger.warning("Category 'viral' (Shorts Tin Độc Lạ) is temporarily DISABLED. Skipping run.")
        summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary_file:
            try:
                Path(summary_file).write_text(
                    "## ⏸️ Shorts Tin Độc Lạ (viral) đang tạm tắt\n"
                    "Bỏ qua lần chạy này cho đến khi có cách làm chất lượng hơn.\n",
                    encoding="utf-8",
                )
            except Exception:
                pass
        return 0

    aspect_ratio = args.aspect_ratio or default_ar
    max_topics = args.max_topics or default_topics

    logger.info("==================================================================")
    logger.info("  STARTING AUTOMATED NEWS BROADCAST (CI / CLOUD RUNNER)")
    logger.info("  Category    : %s", category)
    logger.info("  Aspect Ratio: %s", aspect_ratio)
    logger.info("  Max Topics  : %d", max_topics)
    logger.info("  YouTube     : %s", args.youtube)
    logger.info("  Quick Test  : %s", args.quick_test)
    logger.info("==================================================================")

    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "run_daily_news.py"),
        "--now",
        "--category",
        category,
        "--aspect-ratio",
        aspect_ratio,
        "--max-topics",
        str(max_topics),
    ]

    if args.youtube:
        cmd.append("--youtube")
    else:
        cmd.append("--no-youtube")

    if args.quick_test:
        cmd.append("--quick-test")

    env = os.environ.copy()
    env["PYTHONPATH"] = f"{PROJECT_ROOT / 'src'}{os.pathsep}{env.get('PYTHONPATH', '')}"
    env["PYTHONIOENCODING"] = "utf-8"

    res = subprocess.run(cmd, env=env)

    # Locate the most recent social_publish_manifest.json.
    # daily_news.py writes to: runtime/data/daily_news/{norm_cat}_{date_str}/social_publish_manifest.json
    # We search both locations for backward compatibility.
    manifest_data = {}
    search_roots = [
        PROJECT_ROOT / "runtime" / "data" / "daily_news",  # correct location (daily_news.py)
        PROJECT_ROOT / "runtime" / "daily_news",           # legacy fallback
    ]
    candidate_manifests = []
    for search_root in search_roots:
        if search_root.is_dir():
            candidate_manifests.extend(search_root.glob("*/social_publish_manifest.json"))
    candidate_manifests = sorted(
        candidate_manifests,
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if candidate_manifests:
        try:
            manifest_data = json.loads(candidate_manifests[0].read_text(encoding="utf-8"))
            logger.info("Loaded manifest from: %s", candidate_manifests[0])
            # Sync a copy to the well-known central path
            central_manifest = PROJECT_ROOT / "runtime" / "data" / "social_publish_manifest.json"
            central_manifest.parent.mkdir(parents=True, exist_ok=True)
            central_manifest.write_text(
                json.dumps(manifest_data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except Exception as sync_exc:
            logger.warning("Could not sync central social_publish_manifest.json: %s", sync_exc)
    else:
        logger.warning("No social_publish_manifest.json found after run (searched: %s)", search_roots)

    # Write execution report to GitHub Step Summary
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_file:
        try:
            yt_published = manifest_data.get("youtube_published", False)
            yt_url = manifest_data.get("youtube_url", "")
            yt_error = manifest_data.get("youtube_error", "")
            title = manifest_data.get("title", f"Bản Tin {category}")
            summary_lines = [
                f"## 🎬 HaizFlow Broadcast Pipeline Summary",
                f"- **Tiêu đề**: **{title}**",
                f"- **Chủ đề**: `{category}` ({aspect_ratio})",
                f"- **Số sự kiện**: `{max_topics}`",
                f"- **Mã thoát tiến trình**: `exit_code={res.returncode}`",
                "",
            ]
            if args.youtube:
                if yt_published and yt_url:
                    summary_lines.extend([
                        "### ✅ Xuất Bản YouTube: THÀNH CÔNG",
                        f"- 🔗 **Xem video**: [{yt_url}]({yt_url})",
                        f"- 🆔 **Video ID**: `{manifest_data.get('youtube_video_id', '')}`",
                    ])
                    if manifest_data.get("youtube_playlist_title"):
                        summary_lines.append(f"- 📺 **Playlist**: {manifest_data.get('youtube_playlist_title')}")
                else:
                    summary_lines.extend([
                        "### ❌ Xuất Bản YouTube: KHÔNG THÀNH CÔNG",
                        f"- ⚠️ **Lý do**: {yt_error or 'Không tìm thấy OAuth Token hoặc xác thực bị lỗi'}",
                        "",
                        "**Hướng dẫn khắc phục:**",
                        "1. Vào **Settings** > **Secrets and variables** > **Actions** trên GitHub.",
                        "2. Đảm bảo đã thiết lập đủ 2 secrets: `YOUTUBE_TOKEN_JSON` và `YOUTUBE_CLIENT_SECRET_JSON`.",
                        "3. Nếu token đã quá 7 ngày (Google OAuth App ở chế độ 'Testing'), chạy `python scripts/setup_youtube_auth.py` trên máy tính để cấp lại token mới và cập nhật vào Secret.",
                    ])
            else:
                summary_lines.append("ℹ️ *Chế độ không đăng tải YouTube (--no-youtube) được kích hoạt.*")

            Path(summary_file).write_text("\n".join(summary_lines) + "\n", encoding="utf-8")
        except Exception as sum_exc:
            logger.warning("Could not write GITHUB_STEP_SUMMARY: %s", sum_exc)

    return res.returncode


if __name__ == "__main__":
    sys.exit(main())
