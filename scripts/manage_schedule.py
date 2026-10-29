"""Windows Task Scheduler Manager for HaizFlow Automated Daily News.

Allows creating, querying, running, and deleting daily automated broadcast generation
tasks in Windows Task Scheduler for each news category (world, tech, sports).
Runs silently in the background without needing PowerShell execution policies or
keeping the HaizFlow GUI open.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

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

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYTHON_EXE = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
PYTHONW_EXE = PROJECT_ROOT / ".venv" / "Scripts" / "pythonw.exe"
RUNNER_SCRIPT = PROJECT_ROOT / "scripts" / "run_daily_news.py"

TASK_NAMES = {
    "tin_moi": "HaizFlow_DailyNews_tin_moi",
    "hope": "HaizFlow_DailyNews_hope",
    "ai": "HaizFlow_DailyNews_ai",
}

LEGACY_TASK_NAMES = {
    "tin_moi": ["HaizFlow_DailyWorldNews", "HaizFlow_Daily_News", "HaizFlow_DailyNews_world", "HaizFlow_DailyNews_sports", "HaizFlow_DailyNews_tin_nong"],
    "hope": [],
    "ai": ["HaizFlow_DailyNews_tech"],
}

DEFAULT_SCHEDULE_TIMES = {
    "tin_moi": "06:00",
    "hope": "12:00",
    "ai": "17:30",
}


def get_task_name(category: str) -> str:
    cat = category.strip().lower()
    return TASK_NAMES.get(cat, f"HaizFlow_DailyNews_{cat}")


def get_task_command(
    category: str = "tin_moi",
    aspect_ratio: str = "16:9",
    max_topics: int = 9,
    upload_youtube: Optional[bool] = None,
) -> str:
    cat_norm = category.strip().lower()
    # Enforce aspect ratio: Only hope and ai are 9:16 Shorts (1 topic), tin_moi is 16:9 widescreen (9 topics)
    is_short = cat_norm in ("hope", "ai", "tinvui", "hyvong", "ai_tech", "tin_ai")
    ar = "9:16" if is_short else "16:9"
    effective_topics = 1 if is_short else (9 if max_topics in (3, 7, 8) else max_topics)

    if PYTHONW_EXE.is_file():
        py_path = str(PYTHONW_EXE.resolve())
    elif PYTHON_EXE.is_file():
        py_path = str(PYTHON_EXE.resolve())
    else:
        py_path = sys.executable
    script_path = str(RUNNER_SCRIPT.resolve())
    cmd = f'"{py_path}" "{script_path}" --now --category {category} --aspect-ratio {ar} --max-topics {effective_topics}'

    should_yt = upload_youtube
    if should_yt is None:
        settings_file = PROJECT_ROOT / "runtime" / "data" / "daily_news_settings.json"
        if settings_file.is_file():
            try:
                s_data = json.loads(settings_file.read_text(encoding="utf-8"))
                should_yt = bool(s_data.get("auto_upload_youtube", False))
            except Exception:
                should_yt = False

    if should_yt:
        cmd += " --youtube"
    return cmd


def query_task(category: str = "world") -> bool:
    """Check if the scheduled task is currently registered in Windows."""
    task_name = get_task_name(category)
    cmd = ["schtasks", "/Query", "/TN", task_name]
    res = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if res.returncode == 0:
        print(f"\n[ĐÃ ĐĂNG KÝ] Tác vụ '{task_name}' đang hoạt động trong Windows Task Scheduler:")
        print(res.stdout.strip())
        return True

    # Check legacy task names if category is world
    for leg in LEGACY_TASK_NAMES.get(category, []):
        cmd_leg = ["schtasks", "/Query", "/TN", leg]
        res_leg = subprocess.run(
            cmd_leg,
            capture_output=True,
            text=True,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if res_leg.returncode == 0:
            print(f"\n[ĐÃ ĐĂNG KÝ (Legacy)] Tác vụ '{leg}' đang hoạt động trong Windows Task Scheduler:")
            print(res_leg.stdout.strip())
            return True

    print(f"\n[CHƯA ĐĂNG KÝ] Tác vụ '{task_name}' hiện chưa có trong Windows Task Scheduler.")
    return False


def create_task(
    category: str = "world",
    time_str: str = "05:00",
    wake_up: bool = True,
    aspect_ratio: str = "16:9",
    max_topics: int = 8,
    upload_youtube: Optional[bool] = None,
) -> bool:
    """Create or update the daily scheduled task in Windows for a specific category."""
    cat_norm = category.strip().lower()
    ar = "9:16" if cat_norm in ("hope", "ai", "tinvui", "hyvong", "ai_tech", "tin_ai") else "16:9"
    task_name = get_task_name(category)
    task_run_cmd = get_task_command(category, ar, max_topics, upload_youtube=upload_youtube)

    cat_labels = {
        "tin_moi": "Bản Tin Nóng (Thế giới + Chiến sự + Thể thao 16:9)",
        "hope": "Shorts Tin Vui (Y khoa & Hy vọng 9:16)",
        "ai": "Shorts Tin AI (Đột phá Trí tuệ nhân tạo 9:16)",
    }
    label = cat_labels.get(category, category)

    print("=" * 70)
    print(f"  HAIZFLOW - THIẾT LẬP LỊCH TỰ ĐỘNG LÀM VIDEO: {label.upper()}")
    print("=" * 70)
    print(f" - Tên tác vụ : {task_name}")
    print(f" - Chủ đề     : {category}")
    print(f" - Thời gian  : {time_str} mỗi ngày")
    print(f" - Lệnh chạy  : {task_run_cmd}")
    print(f" - Wake PC    : {'BẬT (Đánh thức khi máy Sleep)' if wake_up else 'TẮT'}")
    print(" - Cơ chế     : Tự động chạy ngầm dưới nền Windows (không cần mở app HaizFlow)")
    print("=" * 70)

    cmd = [
        "schtasks",
        "/Create",
        "/SC", "DAILY",
        "/TN", task_name,
        "/TR", task_run_cmd,
        "/ST", time_str,
        "/F",
    ]
    res = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if res.returncode == 0:
        # Configure WakeToRun, StartWhenAvailable, and battery resiliency via PowerShell
        wake_val = "$true" if wake_up else "$false"
        ps_wake = [
            "powershell.exe",
            "-NoProfile",
            "-Command",
            f'$t = Get-ScheduledTask -TaskName "{task_name}"; '
            f'$t.Actions[0].WorkingDirectory = "{PROJECT_ROOT}"; '
            f'$t.Settings.WakeToRun = {wake_val}; '
            f'$t.Settings.StartWhenAvailable = $true; '
            f'$t.Settings.DisallowStartIfOnBatteries = $false; '
            f'$t.Settings.StopIfGoingOnBatteries = $false; '
            f'$t.Settings.ExecutionTimeLimit = "PT2H"; '
            f'Set-ScheduledTask -InputObject $t | Out-Null',
        ]
        subprocess.run(
            ps_wake,
            capture_output=True,
            text=True,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

        # Also ensure Windows power scheme allows wake timers
        if wake_up:
            for flag in ("SCHEME_CURRENT",):
                subprocess.run(
                    ["powercfg", "/setacvalueindex", flag, "SUB_SLEEP", "RTCWAKE", "1"],
                    capture_output=True,
                    check=False,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                subprocess.run(
                    ["powercfg", "/setdcvalueindex", flag, "SUB_SLEEP", "RTCWAKE", "1"],
                    capture_output=True,
                    check=False,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                subprocess.run(
                    ["powercfg", "/setactive", flag],
                    capture_output=True,
                    check=False,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )

        # Cleanup legacy task names for this category to prevent duplicate runs
        for leg in LEGACY_TASK_NAMES.get(category, []):
            if leg != task_name:
                subprocess.run(
                    ["schtasks", "/Delete", "/TN", leg, "/F"],
                    capture_output=True,
                    text=True,
                    check=False,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )

        print(f"\n[THÀNH CÔNG] Đã lên lịch bản tin '{label}' chạy hàng ngày lúc {time_str}!")
        return True
    else:
        print(f"\n[LỖI] Không thể tạo tác vụ trong Windows Task Scheduler: {res.stderr.strip()}")
        return False


def delete_task(category: str = "world") -> bool:
    """Remove the scheduled task from Windows."""
    task_name = get_task_name(category)
    cmd = ["schtasks", "/Delete", "/TN", task_name, "/F"]
    res = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )

    success = (res.returncode == 0)

    # Also clean up legacy tasks
    for leg in LEGACY_TASK_NAMES.get(category, []):
        res_leg = subprocess.run(
            ["schtasks", "/Delete", "/TN", leg, "/F"],
            capture_output=True,
            text=True,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if res_leg.returncode == 0:
            success = True

    if success:
        print(f"\n[ĐÃ HỦY] Đã xóa thành công tác vụ '{task_name}' khỏi Windows Task Scheduler.")
        return True
    else:
        print(f"\n[THÔNG BÁO] Không tìm thấy tác vụ '{task_name}' để xóa.")
        return False


def run_now(category: str = "world") -> bool:
    """Trigger the scheduled task immediately on demand."""
    task_name = get_task_name(category)
    cmd = ["schtasks", "/Run", "/TN", task_name]
    res = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if res.returncode == 0:
        print(f"\n[KÍCH HOẠT] Đã kích hoạt tác vụ '{task_name}' chạy ngầm thành công!")
        return True
    else:
        print(f"\n[LỖI] Không thể kích hoạt tác vụ: {res.stderr.strip()}")
        return False


def clean_legacy_tasks() -> int:
    """Delete all legacy/old individual broadcast tasks from Windows Task Scheduler."""
    legacy_all = [
        "HaizFlow_DailyWorldNews",
        "HaizFlow_Daily_News",
        "HaizFlow_DailyNews_world",
        "HaizFlow_DailyNews_war",
        "HaizFlow_DailyNews_tech",
        "HaizFlow_DailyNews_sports",
        "HaizFlow_DailyNews_viral",
        "HaizFlow_DailyNews_tin_nong",
    ]
    deleted = 0
    print("\n[DỌN DẸP LỊCH CŨ] Đang kiểm tra và gỡ bỏ các tác vụ lập lịch cũ...")
    for task in legacy_all:
        res = subprocess.run(
            ["schtasks", "/Delete", "/TN", task, "/F"],
            capture_output=True,
            text=True,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if res.returncode == 0:
            print(f" -> Đã gỡ bỏ tác vụ cũ: {task}")
            deleted += 1
    print(f"[HOÀN TẤT] Đã gỡ bỏ {deleted} tác vụ cũ khỏi Windows Task Scheduler.")
    return deleted


def main() -> int:
    parser = argparse.ArgumentParser(description="HaizFlow Windows Schedule Manager")
    parser.add_argument(
        "--action",
        choices=["create", "delete", "status", "query", "trigger", "run", "clean_legacy"],
        default=None,
        help="Hành động cần thực hiện",
    )
    parser.add_argument(
        "--category",
        choices=["tin_moi", "hope", "ai"],
        default="tin_moi",
        help="Danh mục bản tin cần lên lịch (tin_moi, hope, ai)",
    )
    parser.add_argument("--time", default=None, help="Giờ chạy hàng ngày (định dạng HH:MM, mặc định theo chuyên mục)")
    parser.add_argument("--aspect-ratio", default=None, choices=["16:9", "9:16", "1:1"], help="Khung hình video")
    parser.add_argument("--max-topics", type=int, default=8, help="Số lượng sự kiện quốc tế")
    parser.add_argument(
        "--wake",
        dest="wake_up",
        action="store_true",
        default=True,
        help="Bật đánh thức máy tính dậy từ Sleep",
    )
    parser.add_argument(
        "--no-wake",
        dest="wake_up",
        action="store_false",
        help="Không đánh thức máy tính dậy từ Sleep",
    )
    parser.add_argument(
        "--youtube",
        dest="upload_youtube",
        action="store_true",
        default=None,
        help="Bật tự động đăng video lên YouTube sau khi hoàn tất",
    )
    parser.add_argument(
        "--no-youtube",
        dest="upload_youtube",
        action="store_false",
        help="Không tự động đăng video lên YouTube",
    )

    # Shorthand flags
    parser.add_argument("--status", action="store_true", help="Kiểm tra trạng thái lịch chạy hiện tại")
    parser.add_argument("--delete", action="store_true", help="Xóa lịch chạy tự động")
    parser.add_argument("--trigger", action="store_true", help="Kích hoạt chạy ngay lập tức qua Task Scheduler")
    parser.add_argument("--clean-legacy", action="store_true", help="Gỡ bỏ toàn bộ tác vụ lập lịch theo cách cũ")

    args = parser.parse_args()

    # Determine action
    action = args.action
    if not action:
        if args.clean_legacy:
            action = "clean_legacy"
        elif args.delete:
            action = "delete"
        elif args.status:
            action = "status"
        elif args.trigger:
            action = "trigger"
        else:
            action = "create"

    if action == "clean_legacy":
        clean_legacy_tasks()
        return 0
    elif action in {"status", "query"}:
        return 0 if query_task(args.category) else 1
    elif action == "delete":
        return 0 if delete_task(args.category) else 1
    elif action in {"trigger", "run"}:
        return 0 if run_now(args.category) else 1
    elif action == "create":
        sched_time = args.time or DEFAULT_SCHEDULE_TIMES.get(args.category, "06:00")
        ar = args.aspect_ratio or ("9:16" if args.category in ("hope", "ai") else "16:9")
        default_topics = 1 if args.category in ("hope", "ai") else 9
        topics_val = default_topics if args.max_topics in (7, 8) else args.max_topics
        ok = create_task(
            category=args.category,
            time_str=sched_time,
            wake_up=args.wake_up,
            aspect_ratio=ar,
            max_topics=topics_val,
            upload_youtube=args.upload_youtube,
        )
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
