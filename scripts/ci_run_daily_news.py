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
from datetime import datetime, timedelta, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ci_daily_news")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT))

VN_TZ = timezone(timedelta(hours=7))


def _get_history_file() -> Path:
    return PROJECT_ROOT / "runtime" / "data" / "daily_news" / "published_news_history.json"


def has_category_run_today(category: str) -> tuple[bool, str]:
    """Check if `category` has already been produced today (Vietnam time UTC+7).

    Protects against GitHub Actions' 3-5 hour schedule queue delays running a second
    time after the user has already triggered `workflow_dispatch` manually.
    """
    history_file = _get_history_file()
    if not history_file.is_file():
        return False, ""

    vn_today = datetime.now(VN_TZ).strftime("%Y-%m-%d")
    slot_key = f"{vn_today}:{category}"

    try:
        raw_data = json.loads(history_file.read_text(encoding="utf-8"))
        if isinstance(raw_data, dict):
            completed_slots = raw_data.get("completed_slots", {})
            if isinstance(completed_slots, dict) and slot_key in completed_slots:
                return True, str(completed_slots[slot_key])
            items = raw_data.get("items", [])
        elif isinstance(raw_data, list):
            items = raw_data
        else:
            items = []

        # Also check recent items in case completed_slots wasn't populated yet
        now_utc = datetime.now(timezone.utc)
        for it in reversed(items):
            if it.get("category") != category:
                continue
            ts = str(it.get("timestamp") or "")
            if not ts:
                continue
            try:
                dt = datetime.fromisoformat(ts[:19]).replace(tzinfo=timezone.utc)
                age_hours = (now_utc - dt).total_seconds() / 3600.0
                if -1.0 <= age_hours <= 10.0:
                    return True, ts
            except Exception:
                pass
    except Exception as exc:
        logger.warning("Could not inspect history for daily slot deduplication: %s", exc)

    return False, ""


def mark_category_completed_today(category: str) -> None:
    """Record that `category` completed for today's VN date in published_news_history.json."""
    history_file = _get_history_file()
    history_file.parent.mkdir(parents=True, exist_ok=True)
    vn_now = datetime.now(VN_TZ)
    vn_today = vn_now.strftime("%Y-%m-%d")
    slot_key = f"{vn_today}:{category}"

    try:
        raw_data: dict = {"items": [], "completed_slots": {}}
        if history_file.is_file():
            loaded = json.loads(history_file.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                raw_data = loaded
            elif isinstance(loaded, list):
                raw_data = {"items": loaded, "completed_slots": {}}
        if not isinstance(raw_data.get("completed_slots"), dict):
            raw_data["completed_slots"] = {}
        raw_data["completed_slots"][slot_key] = vn_now.isoformat()
        history_file.write_text(json.dumps(raw_data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Marked daily slot completed: %s -> %s", slot_key, vn_now.isoformat())
    except Exception as exc:
        logger.warning("Could not mark daily slot completed: %s", exc)


def rollback_last_batch_for_category(category: str) -> int:
    """Remove the most recent batch of published items for `category` from history.

    Used when `--redo-last` (`redo_last=true` in GitHub Actions) is selected so that
    if the previous video had a bug or needed a remake, those exact stories are not skipped.
    """
    history_file = _get_history_file()
    if not history_file.is_file():
        return 0

    try:
        loaded = json.loads(history_file.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            items = list(loaded.get("items", []))
            completed_slots = dict(loaded.get("completed_slots", {}))
        elif isinstance(loaded, list):
            items = list(loaded)
            completed_slots = {}
        else:
            return 0

        # Find the latest timestamp for this category
        cat_items_with_ts: list[tuple[int, datetime, dict]] = []
        for idx, it in enumerate(items):
            if it.get("category") != category:
                continue
            ts = str(it.get("timestamp") or "")
            try:
                dt = datetime.fromisoformat(ts[:19])
            except Exception:
                dt = datetime.min
            cat_items_with_ts.append((idx, dt, it))

        if not cat_items_with_ts:
            logger.info("[REDO-LAST] No previous items found in history for category '%s'.", category)
            return 0

        latest_dt = max(x[1] for x in cat_items_with_ts)
        # All items of this category recorded within 120 seconds of latest_dt belong to the last batch
        indices_to_remove: set[int] = set()
        removed_titles: list[str] = []
        if latest_dt != datetime.min:
            for idx, dt, it in cat_items_with_ts:
                if abs((latest_dt - dt).total_seconds()) <= 120.0:
                    indices_to_remove.add(idx)
                    removed_titles.append(str(it.get("title", "")))
        else:
            # Fallback: remove the very last item of this category
            last_idx, _, last_it = cat_items_with_ts[-1]
            indices_to_remove.add(last_idx)
            removed_titles.append(str(last_it.get("title", "")))

        new_items = [it for idx, it in enumerate(items) if idx not in indices_to_remove]
        vn_today = datetime.now(VN_TZ).strftime("%Y-%m-%d")
        completed_slots.pop(f"{vn_today}:{category}", None)

        payload: dict = {"items": new_items}
        if completed_slots:
            payload["completed_slots"] = completed_slots
        history_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        logger.info("==================================================================")
        logger.info("  🔄 [LÀM LẠI TIN TRƯỚC] Đã hoàn tác %d tin gần nhất của chủ đề '%s':", len(indices_to_remove), category)
        for t in removed_titles:
            logger.info("     • %s", t)
        logger.info("==================================================================")
        return len(indices_to_remove)
    except Exception as exc:
        logger.warning("Failed to rollback last batch for category '%s': %s", category, exc)
        return 0

def resolve_category_from_utc() -> tuple[str, str, int]:
    """Auto-detect category, aspect ratio, and topic count from current UTC/VN time.

    Fixed schedule (pre-shifted 3h earlier for GitHub queue):
      - tin_moi: 20:03 UTC (03:03 VN, target ~06:00 VN daily) -> 16:9 (9 topics)
      - hope:    02:03 UTC (09:03 VN, target ~12:03 VN Mon/Wed/Fri - Thứ 2, 4, 6) -> 9:16 (1 deep topic, 30-60s)
      - ai:      02:03 UTC (09:03 VN, target ~12:03 VN Tue/Thu - Thứ 3, 5) -> 9:16 (1 deep topic, 30-60s)
    """
    now_utc = datetime.now(timezone.utc)
    now_vn = datetime.now(VN_TZ)
    hour = now_utc.hour
    minute = now_utc.minute
    total_minutes = hour * 60 + minute
    vn_weekday = now_vn.weekday()  # 0=Mon(T2), 1=Tue(T3), 2=Wed(T4), 3=Thu(T5), 4=Fri(T6), 5=Sat(T7), 6=Sun(CN)

    logger.info("Current UTC time: %02d:%02d | VN weekday: %d", hour, minute, vn_weekday)

    # 1. Bản tin Tin Nóng (tin_moi): 19:00 - 01:30 UTC (02:00 - 08:30 VN) -> 9 tin 16:9
    if total_minutes >= 19 * 60 or total_minutes < 90:
        return "tin_moi", "16:9", 9

    # 2. Khung 12:03 VN: Thứ 3, Thứ 5 (weekday 1, 3) chạy Tin AI; Thứ 2, 4, 6 (hoặc mặc định) chạy Tin Hope
    if vn_weekday in (1, 3):
        return "ai", "9:16", 1
    return "hope", "9:16", 1


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
            "max_topics": 9,
            "aspect_ratio": "16:9",
            "voice_id": "vi-VN-NamMinhNeural",
            "detail_level": "standard",
            "bgm_enabled": True,
            "bgm_volume": 0.08,
            "auto_upload_youtube": True,
            "youtube_privacy": "private",
            "auto_add_to_playlist": True,
            "youtube_playlist_tin_moi": "Bản tin thế giới",
            "youtube_playlist_hope": "Bản tin thế giới",
            "youtube_playlist_ai": "Bản tin thế giới",
            "schedule_time": "06:00",
            "schedule_wake_up": True,
        }
        settings_file.write_text(json.dumps(default_settings, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("Initialized default daily_news_settings.json.")

    has_token = bool(token_env) or token_file.is_file()
    has_secret = bool(secret_env) or secret_file.is_file()
    has_gemini = bool(os.environ.get("GEMINI_API_KEY", "").strip())
    has_gh_models = bool(os.environ.get("GH_MODELS_TOKEN", "").strip() or os.environ.get("GITHUB_TOKEN", "").strip())
    logger.info("------------------------------------------------------------------")
    logger.info("CI Environment Credentials Check:")
    logger.info("  • GEMINI_API_KEY            : %s", "CONFIGURED" if has_gemini else "MISSING")
    logger.info("  • GITHUB_MODELS (GPT-4o)    : %s", "CONFIGURED (Secondary AI Failover)" if has_gh_models else "MISSING")
    logger.info("  • YOUTUBE_TOKEN_JSON        : %s", "CONFIGURED" if has_token else "MISSING (Cannot upload to YouTube!)")
    logger.info("  • YOUTUBE_CLIENT_SECRET_JSON: %s", "CONFIGURED" if has_secret else "MISSING (Needed to refresh expired tokens)")
    logger.info("------------------------------------------------------------------")


def main() -> int:
    parser = argparse.ArgumentParser(description="HaizFlow CI / Cloud Runner for Daily News")
    parser.add_argument(
        "--category",
        choices=["auto", "tin_moi", "hope", "ai"],
        default="auto",
        help="Category to produce: 'tin_moi' (16:9 Broadcast), 'hope' (Shorts Tin Vui), 'ai' (Shorts Tin AI), or 'auto'.",
    )
    parser.add_argument("--aspect-ratio", choices=["16:9", "9:16"], default=None)
    parser.add_argument("--max-topics", type=int, default=None)
    parser.add_argument("--youtube", action="store_true", default=True, help="Upload to YouTube after generation.")
    parser.add_argument("--no-youtube", dest="youtube", action="store_false")
    parser.add_argument(
        "--privacy",
        choices=["private", "unlisted", "public"],
        default="private",
        help="YouTube privacy status (private, unlisted, public). Default: private.",
    )
    parser.add_argument(
        "--redo-last",
        action="store_true",
        help="Rollback the most recent batch of news for this category from history so it can be remade.",
    )
    parser.add_argument("--quick-test", action="store_true", help="Run fast dry-run with mock data.")
    args = parser.parse_args()

    setup_ci_environment()

    # Determine category, aspect ratio, and topic count (strictly 1 Broadcast + 2 Shorts)
    if args.category == "auto":
        category, aspect_ratio, max_topics = resolve_category_from_utc()
    else:
        category = args.category
        if category in ("hope", "ai"):
            aspect_ratio, max_topics = "9:16", 1
        else:
            aspect_ratio, max_topics = "16:9", 9

    if args.aspect_ratio:
        aspect_ratio = args.aspect_ratio
    if args.max_topics:
        max_topics = args.max_topics

    if args.redo_last:
        rollback_last_batch_for_category(category)

    # Prevent duplicate runs when GitHub Actions' cron schedule fires hours late
    # after the user has already triggered workflow_dispatch manually.
    event_name = os.environ.get("GITHUB_EVENT_NAME", "").strip()
    if event_name == "schedule" and not args.quick_test:
        already_ran, prev_ts = has_category_run_today(category)
        if already_ran:
            vn_today = datetime.now(VN_TZ).strftime("%Y-%m-%d")
            logger.info("==================================================================")
            logger.info("  ⏭️  SKIPPING DELAYED SCHEDULE RUN (ALREADY COMPLETED TODAY)")
            logger.info("  Category     : %s", category)
            logger.info("  VN Date      : %s", vn_today)
            logger.info("  Previous Run : %s", prev_ts)
            logger.info("==================================================================")
            summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
            if summary_file:
                try:
                    Path(summary_file).write_text(
                        f"## ⏭️ Bỏ qua lịch tự động bị trễ (`{category}`)\n"
                        f"- Bản tin **`{category}`** của ngày **{vn_today}** đã được xuất bản trước đó (lúc `{prev_ts}`).\n"
                        f"- Tự động hủy lượt chạy `schedule` bị trễ của GitHub để tránh đăng trùng video.\n",
                        encoding="utf-8",
                    )
                except Exception:
                    pass
            return 0

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
        "--privacy",
        args.privacy,
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

    if res.returncode == 0 and not args.quick_test:
        mark_category_completed_today(category)

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
                    gh_repo = os.environ.get("GITHUB_REPOSITORY", "thaipeace/videoFlow").strip() or "thaipeace/videoFlow"
                    secrets_url = f"https://github.com/{gh_repo}/settings/secrets/actions"
                    guide_url = f"https://github.com/{gh_repo}/blob/main/docs/extras/youtube-oauth-setup-guide.vi.md"
                    gcp_client_url = (
                        "https://console.cloud.google.com/auth/clients/"
                        "704435039379-10u7391buoqbdlqqoh6bbe9hf2ahcl0n.apps.googleusercontent.com"
                        "?project=vigilant-shell-512204-r9"
                    )
                    summary_lines.extend([
                        "### ❌ Xuất Bản YouTube: KHÔNG THÀNH CÔNG",
                        f"- ⚠️ **Lý do**: {yt_error or 'Không tìm thấy OAuth Token hoặc xác thực bị lỗi'}",
                        "- ℹ️ **Nguyên nhân**: Do Google yêu cầu domain name để Publish App nên OAuth App đang ở chế độ **Testing** (token tự động hết hạn sau **7 ngày** và cần cấp lại định kỳ).",
                        "",
                        "#### 🛠️ Hướng dẫn lấy lại Token & khắc phục từ đầu (3 bước):",
                        "",
                        "**Bước 1: Lấy `Client secret` / `client_secret.json` trên Google Cloud Console**",
                        f"1. Mở trực tiếp trang OAuth Client của dự án: 👉 **[{gcp_client_url}]({gcp_client_url})**",
                        "2. Tại mục **Client secrets**:",
                        "   - Google chỉ cho phép **tối đa 2 secret** cùng lúc và ẩn mã secret cũ sau khi tạo.",
                        "   - Do đó, nếu đã đủ 2 secret, hãy **xoá 1 secret cũ (bấm biểu tượng thùng rác 🗑️)** → bấm **+ Add secret** để tạo secret mới.",
                        "   - Bấm biểu tượng **Download JSON (⬇️)** để tải file `client_secret_xxxx.json` về máy (hoặc copy trực tiếp chuỗi `Client secret` mới dạng `GOCSPX-...`).",
                        "   - *(Lưu ý: Nếu trên máy tính của bạn vẫn còn lưu sẵn `runtime/data/youtube_client_secret.json` từ lần chạy trước và bạn không xoá secret đó trên Google Cloud, bạn có thể bỏ qua Bước 1 và chạy thẳng Bước 2)*.",
                        "",
                        "**Bước 2: Chạy script trên máy tính để đăng nhập & sinh Token mới**",
                        "1. Mở Terminal (macOS/Linux) hoặc PowerShell (Windows) tại thư mục dự án `videoFlow` và chạy:",
                        "   - Trên **macOS / Linux**: `python3 scripts/setup_youtube_auth.py`",
                        "   - Trên **Windows**: `python scripts/setup_youtube_auth.py`",
                        "   - *(Hoặc truyền trực tiếp file: `python3 scripts/setup_youtube_auth.py --client-secret-file ~/Downloads/client_secret_xxxx.json`)*",
                        "   - *(Hoặc truyền trực tiếp secret: `python3 scripts/setup_youtube_auth.py --client-id \"704435039379-10u7391buoqbdlqqoh6bbe9hf2ahcl0n.apps.googleusercontent.com\" --client-secret \"GOCSPX-...\"`)*",
                        "2. Nếu được hỏi file, kéo-thả file `client_secret_xxxx.json` vừa tải vào cửa sổ Terminal rồi bấm **Enter**.",
                        "3. Trình duyệt sẽ tự mở trang đăng nhập Google: chọn đúng tài khoản Google sở hữu kênh YouTube → nếu hiện cảnh báo *\"Google hasn't verified this app\"*, bấm **Advanced (Nâng cao)** → **Go to ... (unsafe)** → **Continue (Tiếp tục)**.",
                        "4. Quay lại Terminal: script sẽ tự động in ra **2 khối JSON** cho `YOUTUBE_TOKEN_JSON` và `YOUTUBE_CLIENT_SECRET_JSON` (đồng thời lưu tại `runtime/data/youtube_token.json` và `runtime/data/youtube_client_secret.json`).",
                        "",
                        "**Bước 3: Cập nhật 2 Secrets lên GitHub Actions**",
                        f"1. Mở trang cấu hình Secrets của repo: 👉 **[{secrets_url}]({secrets_url})**",
                        "2. Bấm biểu tượng chỉnh sửa (✏️) hoặc **New repository secret** để cập nhật đủ 2 khóa:",
                        "   - **`YOUTUBE_TOKEN_JSON`**: Dán toàn bộ khối JSON thứ nhất từ Terminal vào.",
                        "   - **`YOUTUBE_CLIENT_SECRET_JSON`**: Dán toàn bộ khối JSON thứ hai từ Terminal vào.",
                        f"3. 📖 Xem tài liệu hướng dẫn chi tiết tại: [`docs/extras/youtube-oauth-setup-guide.vi.md`]({guide_url})",
                    ])
            else:
                summary_lines.append("ℹ️ *Chế độ không đăng tải YouTube (--no-youtube) được kích hoạt.*")

            Path(summary_file).write_text("\n".join(summary_lines) + "\n", encoding="utf-8")
        except Exception as sum_exc:
            logger.warning("Could not write GITHUB_STEP_SUMMARY: %s", sum_exc)

    return res.returncode


if __name__ == "__main__":
    sys.exit(main())
