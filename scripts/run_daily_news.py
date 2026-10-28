"""Command-line runner and scheduler for Daily World News automated video generation.

Allows immediate execution (--now), countdown testing (--countdown N), or daily
scheduling (--schedule-at HH:MM).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# Reconfigure UTF-8 encoding for Windows console
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Add src to Python path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from haizflow.core.logging_config import configure_app_logging
from haizflow.core.paths import runtime_data_dir
from haizflow.services.daily_news import (
    ensure_date_in_title,
    format_youtube_description_with_sources,
    produce_daily_news_video,
)

logger = logging.getLogger("haizflow.daily_news_cli")


def run_countdown(seconds: int) -> None:
    """Display an interactive terminal countdown before running."""
    print(f"\n[CHẾ ĐỘ TEST ĐỊNH THỜI GIAN] Đang đếm ngược {seconds} giây để bắt đầu quy trình tự động...")
    for remaining in range(seconds, 0, -1):
        print(f" -> Khởi động sau: {remaining:2d} giây...", end="\r", flush=True)
        time.sleep(1)
    print("\n -> [BẮT ĐẦU] Thời gian đã đến! Đang kích hoạt pipeline...\n")


def wait_until_target_time(target_time_str: str) -> None:
    """Block execution until the target HH:MM is reached (daily schedule)."""
    target_hour, target_minute = map(int, target_time_str.split(":"))
    now = datetime.now()
    target_dt = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)

    if target_dt <= now:
        # Target time for today has passed, schedule for tomorrow
        target_dt += timedelta(days=1)

    print(f"\n[CHẾ ĐỘ ĐỊNH THỜI GIAN HÀNG NGÀY] Đã lên lịch chạy vào lúc: {target_dt.strftime('%H:%M:%S ngày %d/%m/%Y')}")
    while True:
        current_now = datetime.now()
        remaining_seconds = int((target_dt - current_now).total_seconds())
        if remaining_seconds <= 0:
            print("\n -> [BẮT ĐẦU] Đã đến giờ kích hoạt bản tin thế giới tự động!\n")
            break

        hours, rem = divmod(remaining_seconds, 3600)
        minutes, secs = divmod(rem, 60)
        print(
            f" [Đang chờ đến {target_time_str}] Còn lại: {hours:02d}h {minutes:02d}m {secs:02d}s...",
            end="\r",
            flush=True,
        )
        time.sleep(min(1.0, max(0.2, remaining_seconds)))


def progress_logger(percent: int, message: str) -> None:
    """Print clean terminal progress bar."""
    bar_len = 25
    filled = int(round(bar_len * percent / 100))
    bar = "=" * filled + "-" * (bar_len - filled)
    print(f"[{percent:3d}%] [{bar}] {message}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="HaizFlow Automated Daily World News Video Generator"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--now",
        action="store_true",
        default=True,
        help="Chạy pipeline ngay lập tức để test kết quả (Mặc định).",
    )
    group.add_argument(
        "--countdown",
        type=int,
        metavar="SECS",
        help="Đếm ngược N giây trước khi chạy (ví dụ --countdown 10 để test cơ chế hẹn giờ).",
    )
    group.add_argument(
        "--schedule-at",
        type=str,
        metavar="HH:MM",
        help="Đặt giờ chạy cố định mỗi ngày (ví dụ --schedule-at 05:00 cho 5h sáng).",
    )

    parser.add_argument(
        "--aspect-ratio",
        choices=["16:9", "9:16", "1:1"],
        default="16:9",
        help="Tỉ lệ khung hình video: 16:9 (YouTube 1080p ngang mặc định) hoặc 9:16 (Shorts/TikTok/Reels).",
    )
    parser.add_argument(
        "--voice",
        default="multi_trio",
        help="Giọng đọc: 'multi_trio' (Luân phiên 3 BTV: Nam Minh + Hoài My + Chuyên gia), 'vi-VN-NamMinhNeural', hoặc 'vi-VN-HoaiMyNeural'.",
    )
    parser.add_argument(
        "--detail-level",
        choices=["concise", "standard", "deep"],
        default="standard",
        help="Độ sâu thông tin: 'concise' (nhanh gọn 2-3p), 'standard' (toàn diện 3-4.5p, mặc định), 'deep' (chuyên sâu 4-6p).",
    )
    parser.add_argument(
        "--category",
        choices=[
            "tin_moi", "tin_nong", "morning", "evening", "world_sports", "war_tech",
            "world", "war", "tech", "sports", "viral", "hope", "ai", "ai_tech", "tin_ai",
            "thoisu", "chiensu", "congnghe", "thethao", "tinla", "docla", "tinvui", "tin_vui", "hyvong"
        ],
        default="tin_moi",
        help="Chủ đề bản tin: 'tin_moi' (Bản tin mới: Thế giới + Chiến sự + Thể thao 16:9), 'hope' (Short Tin vui 9:16), 'ai' (Short Tin AI đột phá 9:16). Mặc định: tin_moi.",
    )
    parser.add_argument(
        "--max-topics", 
        type=int,
        default=8,
        help="Số lượng sự kiện quốc tế tiêu biểu trong bản tin YouTube (mặc định: 8 sự kiện).",
    )
    parser.add_argument(
        "--quick-test",
        action="store_true",
        help="Chế độ test nhanh với mock data để xuất video trong vài giây.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="",
        help="Thư mục xuất video (mặc định lưu trong runtime/daily_news).",
    )
    parser.add_argument(
        "--bgm",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Bật nhạc nền hào hứng thật nhỏ dưới giọng đọc (mặc định: bật).",
    )
    parser.add_argument(
        "--bgm-path",
        type=str,
        default="",
        help="Đường dẫn file nhạc nền tuỳ chỉnh (mặc định: news_bgm.wav của HaizFlow).",
    )
    parser.add_argument(
        "--bgm-volume",
        type=float,
        default=0.08,
        help="Âm lượng nhạc nền thật nhỏ (0.01 - 0.20, mặc định: 0.08).",
    )
    parser.add_argument(
        "--youtube",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Tự động đăng lên YouTube (mặc định: lấy theo cài đặt HaizFlow).",
    )
    parser.add_argument(
        "--privacy",
        choices=["private", "unlisted", "public"],
        default=None,
        help="Chế độ hiển thị YouTube: private, unlisted, public (mặc định: private).",
    )
    parser.add_argument(
        "--prefer-real-images",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Ưu tiên ảnh chụp thật từ bài báo (Fair Use Social Card). Đặt --no-prefer-real-images để dùng 100%% ảnh AI thuần túy (Zero-Copyright).",
    )

    args = parser.parse_args()
    configure_app_logging()

    # Load social upload settings
    from haizflow.config import RUNTIME_DATA_DIR
    settings_file = Path(RUNTIME_DATA_DIR) / "daily_news_settings.json"
    cfg_auto_yt = False
    yt_privacy = args.privacy or "private"
    s_data: dict = {}
    if settings_file.is_file():
        try:
            s_data = json.loads(settings_file.read_text(encoding="utf-8"))
            cfg_auto_yt = bool(s_data.get("auto_upload_youtube", False))
            yt_privacy = args.privacy or str(s_data.get("youtube_privacy", "private"))
        except Exception:
            pass

    should_upload_yt = args.youtube if args.youtube is not None else cfg_auto_yt

    cat_norm = args.category.strip().lower()
    aspect_ratio_to_use = args.aspect_ratio
    max_topics_to_use = args.max_topics
    if cat_norm in ("viral", "tinla", "docla", "hope", "tinvui", "tin_vui", "hyvong", "ai", "ai_tech", "tin_ai"):
        aspect_ratio_to_use = "9:16"
        if max_topics_to_use is None or max_topics_to_use <= 0 or max_topics_to_use in (3, 7, 8, 9):
            max_topics_to_use = 1
    elif cat_norm in ("tin_moi", "morning"):
        aspect_ratio_to_use = "16:9"
        if max_topics_to_use is None or max_topics_to_use == 8:
            max_topics_to_use = 9
    else:
        # Standard long-form news (world, war, tech, sports) must strictly be 16:9 widescreen
        aspect_ratio_to_use = "16:9"

    print("=" * 70)
    print("  HAIZFLOW - BẢN TIN THẾ GIỚI TỰ ĐỘNG (AUTOMATED WORLD NEWS)")
    print("=" * 70)
    print(" - Nguồn tin: 100% Tin quốc tế (Đã lọc bỏ tin Việt Nam)")
    print(" - Kịch bản: Gemini Flash biên tập tiếng Việt")
    print(f" - Mức độ chi tiết: {args.detail_level.upper()} ({max_topics_to_use} sự kiện chuyên sâu)")
    print(" - Ảnh tư liệu: Wikimedia Commons (Public Domain) + AI Cinematic Fallback")
    print(f" - Khung hình: {aspect_ratio_to_use}")
    print(f" - Giọng đọc: {args.voice}")
    print(f" - Chủ đề: {args.category.upper()}")
    print(f" - Nhạc nền: BẬT (Âm lượng: {int(args.bgm_volume * 100)}% - Nhẹ nhàng tạo hào hứng)" if args.bgm else " - Nhạc nền: TẮT")
    print(f" - Đăng YouTube : {'BẬT' if should_upload_yt else 'TẮT'}")
    print("=" * 70)

    # Timing / Scheduling execution
    if args.schedule_at:
        wait_until_target_time(args.schedule_at)
    elif args.countdown:
        run_countdown(args.countdown)
    else:
        print("\n -> Chạy ngay lập tức theo yêu cầu...\n")

    out_dir = Path(args.output_dir) if args.output_dir else None

    start_time = time.time()
    try:
        video_path = produce_daily_news_video(
            output_dir=out_dir,
            aspect_ratio=aspect_ratio_to_use,
            voice_id=args.voice,
            mock_news=args.quick_test,
            detail_level=args.detail_level,
            max_topics=max_topics_to_use,
            bgm_path=args.bgm_path if (args.bgm and args.bgm_path) else ("default" if args.bgm else ""),
            bgm_volume=args.bgm_volume,
            category=args.category,
            progress_callback=progress_logger,
            prefer_real_images=args.prefer_real_images,
        )
        elapsed = time.time() - start_time
        print("\n" + "=" * 70)
        print(" HOÀN TẤT THÀNH CÔNG!")
        print(f" Video xuất bản tại: {video_path}")
        print(f" Thời gian thực thi: {elapsed:.1f} giây")

        # Automatic Social Media Uploads
        manifest_file = video_path.parent / "social_publish_manifest.json"
        manifest = {}
        if manifest_file.is_file():
            try:
                manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        title = ensure_date_in_title(manifest.get("title", "Bản Tin Thời Sự Thế Giới"), manifest.get("created_at"))
        summary = manifest.get("summary", "")
        # Re-read settings fresh from disk
        if settings_file.is_file():
            try:
                s_data = json.loads(settings_file.read_text(encoding="utf-8"))
                cfg_auto_yt = bool(s_data.get("auto_upload_youtube", False))
                yt_privacy = args.privacy or str(s_data.get("youtube_privacy", "private"))
            except Exception as e:
                logger.warning("Could not re-read settings file: %s", e)

        if args.youtube is not None:
            should_upload_yt = bool(args.youtube)
        else:
            should_upload_yt = cfg_auto_yt

        logger.info(
            "Kiểm tra xuất bản: should_upload_yt=%s (args.youtube=%s, settings_auto_upload_youtube=%s)",
            should_upload_yt,
            args.youtube,
            cfg_auto_yt,
        )

        raw_hashtags = manifest.get("hashtags", "#tintucthegioi #thoisu24h")
        hashtags = " ".join([t for t in raw_hashtags.split() if t.lower().lstrip("#") != "haizflow"])
        post_content = format_youtube_description_with_sources(
            manifest,
            title=title,
            summary=summary,
            hashtags=hashtags,
        )

        if should_upload_yt:
            logger.info("[TỰ ĐỘNG ĐĂNG YOUTUBE] Đang kết nối Google YouTube API...")
            try:
                from haizflow.services import youtube_direct
                if youtube_direct.get_saved_token():
                    tags = [t.strip("# ") for t in hashtags.split() if t and t.lower().strip("# ") != "haizflow"]

                    # Determine target playlist based on category
                    category = manifest.get("category", args.category)
                    target_playlist = None
                    if s_data.get("auto_add_to_playlist", True):
                        if category in ("tin_moi", "morning"):
                            target_playlist = s_data.get("youtube_playlist_tin_moi", s_data.get("youtube_playlist_world", "Bản tin thế giới"))
                        elif category in ("tin_nong", "evening"):
                            target_playlist = s_data.get("youtube_playlist_tin_nong", s_data.get("youtube_playlist_world", "Bản tin thế giới"))
                        elif category in ("tech", "congnghe"):
                            target_playlist = s_data.get("youtube_playlist_tech", "Bản tin thế giới")
                        elif category in ("sports", "thethao"):
                            target_playlist = s_data.get("youtube_playlist_sports", "Bản tin thế giới")
                        elif category in ("viral", "tinla", "docla"):
                            target_playlist = s_data.get("youtube_playlist_viral", "Bản tin thế giới")
                        elif category in ("hope", "tinvui", "tin_vui", "hyvong"):
                            target_playlist = s_data.get("youtube_playlist_hope", "Bản tin thế giới")
                        elif category in ("ai", "ai_tech", "tin_ai"):
                            target_playlist = s_data.get("youtube_playlist_ai", s_data.get("youtube_playlist_tech", "Bản tin thế giới"))
                        elif category in ("war", "chiensu"):
                            target_playlist = s_data.get("youtube_playlist_war", "Bản tin thế giới")
                        else:
                            target_playlist = s_data.get("youtube_playlist_world", "Bản tin thế giới")

                    def _upload_cb(pct: int, msg: str):
                        logger.info("  [YouTube %3d%%] %s", pct, msg)

                    yt_res = youtube_direct.upload_video_to_youtube(
                        video_path=str(video_path),
                        title=title,
                        description=post_content,
                        tags=tags,
                        privacy_status=yt_privacy,
                        playlist_name=target_playlist,
                        progress_callback=_upload_cb,
                        thumbnail_path=manifest.get("thumbnail_path") or None,
                    )
                    thumb_res = yt_res.get("thumbnail")
                    if thumb_res:
                        if thumb_res.get("success"):
                            logger.info("  ✓ Đã đặt thumbnail tùy chỉnh")
                        else:
                            logger.warning("  ! Không đặt được thumbnail (%s)", thumb_res.get("reason", ""))
                    v_url = yt_res.get("url", "")
                    logger.info("  ✓ Đã đăng thành công lên YouTube (%s): %s", yt_privacy, v_url)
                    if yt_res.get("playlist", {}).get("added"):
                        logger.info("  ✓ Đã thêm video vào playlist '%s'", yt_res['playlist'].get('playlist_name', ''))
                    elif yt_res.get("playlist", {}).get("scope_insufficient"):
                        logger.warning("  ! Lưu ý: Chưa cấp quyền quản lý Playlist trên Google YouTube.")

                    # Update manifest on disk
                    manifest["youtube_published"] = True
                    manifest["youtube_video_id"] = yt_res.get("video_id", "")
                    manifest["youtube_url"] = v_url
                    manifest["youtube_published_at"] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                    if yt_res.get("playlist"):
                        manifest["youtube_playlist"] = yt_res.get("playlist")
                        if yt_res.get("playlist", {}).get("added"):
                            manifest["youtube_playlist_title"] = yt_res["playlist"].get("playlist_name", "")
                            manifest["youtube_playlist_id"] = yt_res["playlist"].get("playlist_id", "")
                    manifest_file.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
                else:
                    logger.warning("==================================================================")
                    logger.warning("⚠️  CẢNH BÁO: KHÔNG THỂ ĐĂNG LÊN YOUTUBE!")
                    logger.warning("   Lý do: Chưa có OAuth Token (không tìm thấy youtube_token.json hoặc secret YOUTUBE_TOKEN_JSON).")
                    logger.warning("   -> Vui lòng kiểm tra Secret 'YOUTUBE_TOKEN_JSON' trên GitHub Repository Settings.")
                    logger.warning("==================================================================")
                    manifest["youtube_published"] = False
                    manifest["youtube_error"] = "Chưa kết nối tài khoản Google YouTube (thiếu YOUTUBE_TOKEN_JSON)."
                    manifest_file.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception as yt_err:
                logger.error("==================================================================")
                logger.error("❌  ĐĂNG TẢI YOUTUBE THẤT BẠI: %s", yt_err)
                logger.error("   -> Nếu lỗi 'invalid_grant' hoặc 'Token has been expired or revoked':")
                logger.error("      OAuth Token của Google đã hết hạn (đặc biệt khi Google App ở chế độ 'Testing').")
                logger.error("      Cần tạo lại token mới và cập nhật vào GitHub Secret 'YOUTUBE_TOKEN_JSON'.")
                logger.error("==================================================================")
                manifest["youtube_published"] = False
                manifest["youtube_error"] = str(yt_err)
                manifest_file.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

        print("=" * 70 + "\n")
        return 0
    except Exception as exc:
        logger.exception("Pipeline execution failed: %s", exc)
        print(f"\n[LỖI] Quy trình gặp sự cố: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
