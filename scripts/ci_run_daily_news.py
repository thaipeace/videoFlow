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

SCHEDULE_RULES = [
    # (name, utc_hour_range, min_topics, aspect_ratio)
    # 07:30 VN (UTC+7) = 00:30 UTC
    ("tin_moi", range(0, 3), 8, "16:9"),
    # 11:30 VN (UTC+7) = 04:30 UTC (YouTube Shorts <= 25s)
    ("hope", range(3, 5), 1, "9:16"),
    # 12:00 VN (UTC+7) = 05:00 UTC (YouTube Shorts <= 25s)
    ("viral", range(5, 7), 1, "9:16"),
    # 17:30 VN (UTC+7) = 10:30 UTC
    ("tin_nong", range(9, 13), 8, "16:9"),
]


def resolve_category_from_utc() -> tuple[str, str, int]:
    """Auto-detect category, aspect ratio, and topic count from current UTC time."""
    now_utc = datetime.now(timezone.utc)
    hour = now_utc.hour
    minute = now_utc.minute
    total_minutes = hour * 60 + minute

    logger.info("Current UTC time: %02d:%02d (Hour %d)", hour, minute, hour)

    # 1. Check specific time windows (+- 45 min around target schedules)
    # Target 07:30 VN = 00:30 UTC (30 mins), tolerate GitHub start delays
    if 0 <= total_minutes < 180:
        return "tin_moi", "16:9", 8

    # Target 11:30 VN = 04:30 UTC (270 mins)
    if 240 <= total_minutes < 290:
        return "hope", "9:16", 1

    # Target 12:00 VN = 05:00 UTC (300 mins)
    if 290 <= total_minutes < 360:
        return "viral", "9:16", 1

    # Target 17:30 VN = 10:30 UTC (630 mins)
    if 580 <= total_minutes <= 720:
        return "tin_nong", "16:9", 8

    # Default fallback
    logger.info("Time does not match a specific midday/evening slot. Defaulting to 'tin_moi'.")
    return "tin_moi", "16:9", 8


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


def main() -> int:
    parser = argparse.ArgumentParser(description="HaizFlow CI / Cloud Runner for Daily News")
    parser.add_argument(
        "--category",
        choices=["auto", "tin_moi", "hope", "viral", "tin_nong"],
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
        if category in ("hope", "viral"):
            default_ar, default_topics = "9:16", 1
        else:
            default_ar, default_topics = "16:9", 8

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

    # Post-run Google Drive archival for editorial scripts
    try:
        editorial_dir = PROJECT_ROOT / "runtime" / "data" / "editorial_scripts"
        if editorial_dir.is_dir():
            from scripts.upload_to_gdrive import upload_directory_files
            logger.info("Archiving recent editorial scripts to Google Drive...")
            upload_directory_files(editorial_dir, pattern="*.txt", limit=3)
    except Exception as drive_exc:
        logger.warning("Post-run Google Drive archival skipped or failed: %s", drive_exc)

    return res.returncode


if __name__ == "__main__":
    sys.exit(main())
