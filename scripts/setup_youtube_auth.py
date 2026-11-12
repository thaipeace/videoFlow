#!/usr/bin/env python3
"""Interactive YouTube OAuth Setup & GitHub Secrets Generator.

Helps authenticate your YouTube channel and prints the exact JSON
strings needed for GitHub Actions secrets (YOUTUBE_TOKEN_JSON and YOUTUBE_CLIENT_SECRET_JSON).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

_ORIGINAL_HOME = os.environ.get("HOME", "")

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
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT))

from haizflow.config import RUNTIME_DATA_DIR
from haizflow.services import youtube_direct

if sys.platform != "win32" and _ORIGINAL_HOME:
    os.environ["HOME"] = _ORIGINAL_HOME


def _resolve_user_path(raw: str) -> str:
    cleaned = raw.strip().strip('"\'')
    if not cleaned:
        return ""
    candidate = Path(cleaned).expanduser()
    if candidate.is_file():
        return str(candidate)
    # macOS Terminal escapes spaces with backslashes when dragging files into input()
    unescaped = Path(cleaned.replace("\\ ", " ")).expanduser()
    if unescaped.is_file():
        return str(unescaped)
    return str(candidate)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("setup_youtube_auth")


def main() -> int:
    parser = argparse.ArgumentParser(description="Authenticate YouTube and generate GitHub Secrets.")
    parser.add_argument("--client-secret-file", type=str, help="Path to downloaded client_secret.json from Google Cloud Console.")
    parser.add_argument("--client-id", type=str, help="Google Cloud OAuth Client ID.")
    parser.add_argument("--client-secret", type=str, help="Google Cloud OAuth Client Secret.")
    parser.add_argument("--check-only", action="store_true", help="Only verify existing saved credentials without re-authenticating.")
    args = parser.parse_args()

    runtime_data = Path(RUNTIME_DATA_DIR)
    runtime_data.mkdir(parents=True, exist_ok=True)
    token_file = runtime_data / "youtube_token.json"
    secret_file = runtime_data / "youtube_client_secret.json"

    print("=" * 72)
    print("  HAIZFLOW / VIDEOFLOW - YOUTUBE OAUTH AUTHENTICATION SETUP")
    print("=" * 72)

    if args.check_only:
        token = youtube_direct.get_saved_token()
        client_id, client_secret = youtube_direct.get_client_credentials()
        if not token or not client_id or not client_secret:
            print("\n[!] Chưa có thông tin xác thực YouTube trên máy.")
            return 1
        try:
            ch_info = youtube_direct.get_channel_info()
            print(f"\n[OK] Đã kết nối kênh: {ch_info.get('title', 'Unknown')} (ID: {ch_info.get('id', '')})")
            return 0
        except Exception as exc:
            print(f"\n[ERR] Lỗi xác thực token: {exc}")
            return 1

    # 1. Resolve client credentials
    if args.client_secret_file:
        c_id, c_secret = youtube_direct.import_client_secret_file(_resolve_user_path(args.client_secret_file))
    elif args.client_id and args.client_secret:
        c_id, c_secret = args.client_id.strip(), args.client_secret.strip()
        youtube_direct.save_client_credentials(c_id, c_secret)
    else:
        c_id, c_secret = youtube_direct.get_client_credentials()
        if not c_id or not c_secret:
            print("\n👉 Bạn chưa có Client ID và Client Secret trên máy.")
            print("   Cách lấy trên Google Cloud Console:")
            print("   1. Mở trang OAuth Client:")
            print("      https://console.cloud.google.com/auth/clients/704435039379-10u7391buoqbdlqqoh6bbe9hf2ahcl0n.apps.googleusercontent.com?project=vigilant-shell-512204-r9")
            print("   2. Tại mục 'Client secrets' (chỉ tối đa 2 secret): nếu đã đủ 2 secret thì xoá 1 secret cũ -> bấm '+ Add secret' -> bấm 'Download JSON'.")
            print("   Vui lòng kéo-thả file client_secret.json vào đây (hoặc bấm Enter để nhập thủ công):")
            input_file = _resolve_user_path(input("   Đường dẫn tệp client_secret.json (bấm Enter để nhập thủ công): "))
            if input_file and Path(input_file).is_file():
                c_id, c_secret = youtube_direct.import_client_secret_file(input_file)
            else:
                c_id = input("   Nhập Client ID: ").strip()
                c_secret = input("   Nhập Client Secret: ").strip()
                if c_id and c_secret:
                    youtube_direct.save_client_credentials(c_id, c_secret)
                else:
                    print("\n[!] Thiếu Client ID hoặc Client Secret. Hủy thao tác.")
                    return 1

    print(f"\n[OK] Client ID: {c_id[:20]}...{c_id[-10:] if len(c_id) > 30 else ''}")
    print("-> Đang mở trình duyệt để bạn đăng nhập và cấp quyền cho kênh YouTube...")

    try:
        token_data = youtube_direct.start_oauth_flow(client_id=c_id, client_secret=c_secret)
        print("\n[OK] ĐĂNG NHẬP THÀNH CÔNG!")
    except Exception as exc:
        print(f"\n[ERR] Đăng nhập thất bại: {exc}")
        return 1

    try:
        ch_info = youtube_direct.get_channel_info()
        print(f"-> Kênh đã kết nối: {ch_info.get('title', 'Unknown')} (ID: {ch_info.get('id', '')})")
    except Exception as ch_err:
        print(f"[!] Đã lưu token nhưng không lấy được thông tin kênh: {ch_err}")

    # Prepare JSON secrets for GitHub Actions
    token_json_str = json.dumps(token_data, indent=2)
    client_secret_json_str = secret_file.read_text(encoding="utf-8") if secret_file.is_file() else json.dumps({
        "installed": {
            "client_id": c_id,
            "client_secret": c_secret,
        }
    }, indent=2)

    print("\n" + "=" * 72)
    print("  HƯỚNG DẪN CẬP NHẬT GITHUB SECRETS (ĐỂ GITHUB ACTIONS TỰ UPLOAD)")
    print("=" * 72)
    print("1. Mở trang Secrets của repo:")
    print("   https://github.com/thaipeace/videoFlow/settings/secrets/actions\n")
    print("2. Thêm Secret thứ nhất: Tên = YOUTUBE_TOKEN_JSON")
    print("   Giá trị (Sao chép toàn bộ khối JSON bên dưới):")
    print("-" * 50)
    print(token_json_str)
    print("-" * 50)
    print("\n3. Thêm Secret thứ hai: Tên = YOUTUBE_CLIENT_SECRET_JSON")
    print("   Giá trị (Sao chép toàn bộ khối JSON bên dưới):")
    print("-" * 50)
    print(client_secret_json_str)
    print("-" * 50)
    print("\n[OK] Đã lưu tệp cục bộ tại:")
    print(f"   - {token_file}")
    print(f"   - {secret_file}")
    print("=" * 72 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
