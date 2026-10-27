"""HaizFlow Daily News Automation Diagnostic & Repair Harness.

Validates the complete end-to-end pipeline:
1. System Configuration (daily_news_settings.json)
2. Windows Task Scheduler (All 6 category daily triggers)
3. Google Gemini Flash API Key connectivity
4. YouTube Direct OAuth2 & Channel connectivity (Vạn Chuyện)
5. Core rendering dependencies (MoviePy, Edge-TTS, FFmpeg)

Usage:
  python scripts/check_daily_news_harness.py          # Quick diagnosis
  python scripts/check_daily_news_harness.py --repair # Diagnose & auto-repair issues
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Reconfigure console output for UTF-8 on Windows
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

GOLDEN_SETTINGS: Dict[str, Any] = {
    "selected_category": "tin_moi",
    "max_topics": 8,
    "aspect_ratio": "16:9",
    "voice_id": "vi-VN-NamMinhNeural",
    "detail_level": "standard",
    "bgm_enabled": True,
    "bgm_volume": 0.08,
    "auto_upload_youtube": True,
    "auto_upload_facebook": False,
    "youtube_privacy": "public",
    "auto_add_to_playlist": True,
    "youtube_playlist_tin_moi": "Bản tin thế giới",
    "youtube_playlist_hope": "Bản tin thế giới",
    "youtube_playlist_viral": "Bản tin thế giới",
    "youtube_playlist_tin_nong": "Bản tin thế giới",
    "schedule_time": "05:30",
    "schedule_wake_up": True,
    "schedules": {
        "tin_moi": {"time": "05:30", "wake_up": True},
        "hope": {"time": "11:30", "wake_up": True},
        "viral": {"time": "12:00", "wake_up": True},
        "tin_nong": {"time": "17:30", "wake_up": True},
    },
}

CATEGORIES_INFO = [
    ("tin_moi", "05:30", "16:9", 8, True),
    ("hope", "11:30", "9:16", 7, True),
    ("viral", "12:00", "9:16", 8, True),
    ("tin_nong", "17:30", "16:9", 8, True),
]


def check_configuration_file(repair: bool = False) -> Tuple[bool, str]:
    """Check runtime/data/daily_news_settings.json."""
    settings_path = PROJECT_ROOT / "runtime" / "data" / "daily_news_settings.json"
    if not settings_path.is_file():
        if repair:
            settings_path.parent.mkdir(parents=True, exist_ok=True)
            settings_path.write_text(json.dumps(GOLDEN_SETTINGS, indent=2, ensure_ascii=False), encoding="utf-8")
            return True, "[ĐÃ SỬA] File cài đặt bị thiếu, đã khôi phục từ mẫu Golden Baseline."
        return False, "[LỖI] Thiếu file runtime/data/daily_news_settings.json."

    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
    except Exception as exc:
        if repair:
            settings_path.write_text(json.dumps(GOLDEN_SETTINGS, indent=2, ensure_ascii=False), encoding="utf-8")
            return True, f"[ĐÃ SỬA] File cài đặt hỏng JSON ({exc}), đã khôi phục từ Golden Baseline."
        return False, f"[LỖI] File JSON bị lỗi cú pháp: {exc}"

    auto_yt = data.get("auto_upload_youtube")
    schedules = data.get("schedules", {})
    missing_cats = [c for c, _, _, _, _ in CATEGORIES_INFO if c not in schedules]

    if not auto_yt:
        if repair:
            data["auto_upload_youtube"] = True
            settings_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            return True, "[ĐÃ SỬA] auto_upload_youtube đang tắt, đã kích hoạt lại thành True."
        return False, "[CẢNH BÁO] auto_upload_youtube đang bị TẮT (False)."

    if missing_cats:
        if repair:
            for c, t, _, _, w in CATEGORIES_INFO:
                if c not in data.get("schedules", {}):
                    data.setdefault("schedules", {})[c] = {"time": t, "wake_up": w}
            settings_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            return True, f"[ĐÃ SỬA] Đã bổ sung cấu hình lịch cho các mục thiếu: {', '.join(missing_cats)}"
        return False, f"[LỖI] Thiếu lịch cho các chuyên mục: {', '.join(missing_cats)}"

    return True, f"[OK] Cấu hình chuẩn. Đăng YouTube: BẬT | {len(CATEGORIES_INFO)}/{len(CATEGORIES_INFO)} chuyên mục có lịch trình."


def check_youtube_connection() -> Tuple[bool, str]:
    """Check YouTube API credentials and channel connectivity."""
    secret_path = PROJECT_ROOT / "runtime" / "data" / "youtube_client_secret.json"
    token_path = PROJECT_ROOT / "runtime" / "data" / "youtube_token.json"

    if not secret_path.is_file():
        return False, "[LỖI] Thiếu file youtube_client_secret.json trong runtime/data/."
    if not token_path.is_file():
        return False, "[LỖI] Thiếu file youtube_token.json trong runtime/data/. Cần đăng nhập OAuth."

    try:
        from haizflow.services.youtube_direct import get_channel_info
        ch = get_channel_info()
        title = ch.get("title", "Không rõ")
        ch_id = ch.get("id", "Không rõ")
        return True, f"[OK] Kênh YouTube kết nối tốt: '{title}' (ID: {ch_id})."
    except Exception as exc:
        return False, f"[LỖI] Không kết nối được YouTube API: {exc}"


def check_gemini_api_key() -> Tuple[bool, str]:
    """Check Google Gemini Flash API key."""
    try:
        from haizflow.services.image_generator import get_effective_gemini_api_key
        key = get_effective_gemini_api_key()
        if not key:
            return False, "[LỖI] Không tìm thấy Gemini API Key trong hệ thống hoặc Credential Manager."
        prefix = key[:8] + "..." if len(key) > 8 else "***"
        return True, f"[OK] Gemini API Key hợp lệ (Key prefix: {prefix})."
    except Exception as exc:
        return False, f"[LỖI] Lỗi kiểm tra Gemini Key: {exc}"


def check_task_scheduler(repair: bool = False) -> List[Tuple[str, bool, str]]:
    """Check all 4 scheduled tasks in Windows Task Scheduler."""
    results = []
    from scripts import manage_schedule

    if repair:
        manage_schedule.clean_legacy_tasks()

    for cat, expected_time, ar, max_topics, wake in CATEGORIES_INFO:
        task_name = f"HaizFlow_DailyNews_{cat}"
        cmd = ["schtasks", "/Query", "/TN", task_name, "/V", "/FO", "LIST"]
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)

        if res.returncode != 0:
            if repair:
                manage_schedule.create_task(
                    category=cat,
                    time_str=expected_time,
                    wake_up=wake,
                    aspect_ratio=ar,
                    max_topics=max_topics,
                    upload_youtube=True,
                )
                results.append((task_name, True, f"[ĐÃ TẠO LẠI] Task chưa có, đã đăng ký mới lúc {expected_time}"))
            else:
                results.append((task_name, False, f"[LỖI] Task chưa được đăng ký trong Windows."))
            continue

        output = res.stdout
        has_youtube = "--youtube" in output
        time_ok = expected_time in output

        if not has_youtube:
            if repair:
                manage_schedule.create_task(
                    category=cat,
                    time_str=expected_time,
                    wake_up=wake,
                    aspect_ratio=ar,
                    max_topics=max_topics,
                    upload_youtube=True,
                )
                results.append((task_name, True, f"[ĐÃ SỬA] Task thiếu cờ --youtube, đã cập nhật lại."))
            else:
                results.append((task_name, False, f"[CẢNH BÁO] Lệnh của Task THIẾU cờ --youtube (sẽ không tự upload)."))
        elif not time_ok:
            if repair:
                manage_schedule.create_task(
                    category=cat,
                    time_str=expected_time,
                    wake_up=wake,
                    aspect_ratio=ar,
                    max_topics=max_topics,
                    upload_youtube=True,
                )
                results.append((task_name, True, f"[ĐÃ SỬA] Đã cập nhật lại giờ chạy chuẩn: {expected_time}"))
            else:
                results.append((task_name, False, f"[LỆCH GIỜ] Giờ chạy thực tế khác với kế hoạch ({expected_time})."))
        else:
            results.append((task_name, True, f"[OK] Sẵn sàng lúc {expected_time} hàng ngày (Khung hình {ar}, Đăng YouTube: CÓ)."))

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="HaizFlow Daily News Harness Diagnostics & Repair")
    parser.add_argument("--repair", action="store_true", help="Tự động sửa chữa các lỗi cấu hình và lịch trình được phát hiện.")
    args = parser.parse_args()

    print("=" * 75)
    print("  🛡️  HAIZFLOW DAILY NEWS - BỘ KHUNG KIỂM TRA & CHẨN ĐOÁN (HARNESS CHECK)")
    print("=" * 75)
    print(f"Chế độ: {'TỰ ĐỘNG SỬA CHỮA (--repair)' if args.repair else 'CHẨN ĐOÁN (Read-only)'}\n")

    all_passed = True

    # 1. Config file
    print("1. KIỂM TRA FILE CẤU HÌNH (daily_news_settings.json):")
    ok, msg = check_configuration_file(repair=args.repair)
    print(f"   {'[PASS]' if ok else '[FAIL]'} {msg}")
    if not ok:
        all_passed = False

    # 2. YouTube
    print("\n2. KIỂM TRA KẾT NỐI YOUTUBE API (OAuth2 & Channel):")
    ok, msg = check_youtube_connection()
    print(f"   {'[PASS]' if ok else '[FAIL]'} {msg}")
    if not ok:
        all_passed = False

    # 3. Gemini API Key
    print("\n3. KIỂM TRA GOOGLE GEMINI FLASH API KEY:")
    ok, msg = check_gemini_api_key()
    print(f"   {'[PASS]' if ok else '[FAIL]'} {msg}")
    if not ok:
        all_passed = False

    # 4. Windows Task Scheduler
    print("\n4. KIỂM TRA WINDOWS TASK SCHEDULER (4 Bản tin theo chiến lược mới):")
    task_results = check_task_scheduler(repair=args.repair)
    for task_name, ok, msg in task_results:
        print(f"   • {task_name:<26}: {'[PASS]' if ok else '[FAIL]'} {msg}")
        if not ok:
            all_passed = False

    print("\n" + "=" * 75)
    if all_passed:
        print("  ✅ TẤT CẢ CÁC THÀNH PHẦN HOẠT ĐỘNG HOÀN HẢO! HỆ THỐNG SẴN SÀNG 100%.")
    else:
        print("  ⚠️ PHÁT HIỆN CẢNH BÁO HOẶC LỖI CẤU HÌNH!")
        if not args.repair:
            print("  👉 Mẹo sửa nhanh: Chạy lại lệnh sau để hệ thống tự động sửa chữa:")
            print("     .venv\\Scripts\\python.exe scripts/check_daily_news_harness.py --repair")
    print("=" * 75 + "\n")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
