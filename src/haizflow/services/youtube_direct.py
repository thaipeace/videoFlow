"""Direct Google YouTube Data API v3 integration with OAuth 2.0.

Provides standalone, zero-dependency YouTube channel authentication,
token refresh, channel info retrieval, and resumable video uploads.
"""

from __future__ import annotations

import http.server
import json
import logging
import os
import re
import socket
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from haizflow.config import RUNTIME_DATA_DIR

LOGGER = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"
PLAYLISTS_URL = "https://www.googleapis.com/youtube/v3/playlists"
PLAYLIST_ITEMS_URL = "https://www.googleapis.com/youtube/v3/playlistItems"
THUMBNAILS_SET_URL = "https://www.googleapis.com/upload/youtube/v3/thumbnails/set"

CLIENT_SECRET_FILE = Path(RUNTIME_DATA_DIR) / "youtube_client_secret.json"
TOKEN_FILE = Path(RUNTIME_DATA_DIR) / "youtube_token.json"


class YouTubeAuthError(Exception):
    """Raised when YouTube authentication fails."""
    pass


class YouTubeUploadError(Exception):
    """Raised when video upload fails."""
    pass


def get_client_credentials() -> Tuple[str, str]:
    """Retrieve Client ID and Client Secret from file or environment."""
    # 1. Check file
    if CLIENT_SECRET_FILE.is_file():
        try:
            data = json.loads(CLIENT_SECRET_FILE.read_text(encoding="utf-8"))
            # Format could be installed/web object from Google Cloud
            cfg = data.get("installed") or data.get("web") or data
            client_id = cfg.get("client_id", "").strip()
            client_secret = cfg.get("client_secret", "").strip()
            if client_id and client_secret:
                return client_id, client_secret
        except Exception as exc:
            LOGGER.warning("Could not read %s: %s", CLIENT_SECRET_FILE, exc)

    # 2. Check environment variables
    env_id = os.environ.get("YOUTUBE_CLIENT_ID", "").strip()
    env_secret = os.environ.get("YOUTUBE_CLIENT_SECRET", "").strip()
    return env_id, env_secret


def save_client_credentials(client_id: str, client_secret: str) -> None:
    """Save client credentials to disk."""
    CLIENT_SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "installed": {
            "client_id": client_id.strip(),
            "client_secret": client_secret.strip(),
            "auth_uri": AUTH_URL,
            "token_uri": TOKEN_URL,
        }
    }
    CLIENT_SECRET_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def import_client_secret_file(file_path: str) -> Tuple[str, str]:
    """Import an existing client_secret.json file downloaded from Google Cloud."""
    p = Path(file_path).resolve()
    if not p.is_file():
        raise FileNotFoundError(f"Tệp không tồn tại: {file_path}")

    data = json.loads(p.read_text(encoding="utf-8"))
    cfg = data.get("installed") or data.get("web") or data
    client_id = cfg.get("client_id", "").strip()
    client_secret = cfg.get("client_secret", "").strip()

    if not client_id or not client_secret:
        raise ValueError("Tệp client_secret.json không hợp lệ hoặc thiếu client_id / client_secret.")

    save_client_credentials(client_id, client_secret)
    return client_id, client_secret


def get_saved_token() -> Optional[Dict[str, Any]]:
    """Load saved OAuth tokens from disk."""
    if not TOKEN_FILE.is_file():
        return None
    try:
        return json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        LOGGER.warning("Could not read token file: %s", exc)
        return None


def has_playlist_permission() -> bool:
    """Check if saved OAuth token contains permissions to manage playlists."""
    token = get_saved_token()
    if not token:
        return False
    scope_str = str(token.get("scope", ""))
    scopes = set(scope_str.split())
    return (
        "https://www.googleapis.com/auth/youtube" in scopes
        or "https://www.googleapis.com/auth/youtube.force-ssl" in scopes
    )


def save_token(token_data: Dict[str, Any]) -> None:
    """Save OAuth tokens to disk."""
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(json.dumps(token_data, indent=2), encoding="utf-8")


def clear_saved_token() -> None:
    """Remove saved token (logout)."""
    if TOKEN_FILE.is_file():
        try:
            TOKEN_FILE.unlink()
        except Exception:
            pass


def refresh_access_token(refresh_token: str, client_id: str, client_secret: str) -> Dict[str, Any]:
    """Exchange a refresh token for a fresh access token."""
    post_data = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }).encode("utf-8")

    req = urllib.request.Request(
        TOKEN_URL,
        data=post_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            data["refresh_token"] = refresh_token  # Preserve refresh token
            data["obtained_at"] = time.time()
            save_token(data)
            return data
    except Exception as exc:
        raise YouTubeAuthError(f"Không thể làm mới token Google: {exc}") from exc


def get_valid_access_token() -> str:
    """Retrieve an active access token, refreshing if necessary."""
    token = get_saved_token()
    if not token or not token.get("refresh_token"):
        raise YouTubeAuthError("Chưa kết nối tài khoản YouTube. Vui lòng kết nối tài khoản trước.")

    obtained_at = float(token.get("obtained_at", 0))
    expires_in = float(token.get("expires_in", 3600))
    # Refresh 60 seconds before expiration
    if time.time() - obtained_at > (expires_in - 60):
        client_id, client_secret = get_client_credentials()
        if not client_id or not client_secret:
            raise YouTubeAuthError("Thiếu Client ID hoặc Client Secret của Google.")
        token = refresh_access_token(token["refresh_token"], client_id, client_secret)

    return token["access_token"]


def get_channel_info(access_token: Optional[str] = None) -> Dict[str, Any]:
    """Retrieve authenticated YouTube channel title and thumbnail."""
    if not access_token:
        access_token = get_valid_access_token()

    url = f"{CHANNELS_URL}?part=snippet&mine=true"
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {access_token}"},
        method="GET",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            items = data.get("items", [])
            if not items:
                return {"title": "Kênh YouTube Cá Nhân", "id": ""}
            snippet = items[0].get("snippet", {})
            return {
                "id": items[0].get("id", ""),
                "title": snippet.get("title", "Kênh YouTube"),
                "description": snippet.get("description", ""),
                "customUrl": snippet.get("customUrl", ""),
            }
    except Exception as exc:
        LOGGER.warning("Could not fetch channel info: %s", exc)
        return {"title": "Kênh YouTube đã kết nối", "id": ""}


# -----------------------------------------------------------------------------
# YouTube Playlists Management
# -----------------------------------------------------------------------------

def list_channel_playlists(access_token: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieve playlists belonging to the authenticated YouTube channel."""
    if not access_token:
        access_token = get_valid_access_token()

    url = f"{PLAYLISTS_URL}?part=snippet,contentDetails&mine=true&maxResults=50"
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {access_token}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            items = data.get("items", [])
            results = []
            for it in items:
                snip = it.get("snippet", {})
                results.append({
                    "id": it.get("id", ""),
                    "title": snip.get("title", ""),
                    "description": snip.get("description", ""),
                    "item_count": it.get("contentDetails", {}).get("itemCount", 0),
                })
            return results
    except Exception as exc:
        LOGGER.warning("Could not list playlists: %s", exc)
        return []


def find_playlist_by_title(title: str, access_token: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Find a playlist by title (case-insensitive with normalized whitespace)."""
    target = " ".join(title.strip().lower().split())
    if not target:
        return None
    playlists = list_channel_playlists(access_token=access_token)
    for p in playlists:
        p_title = " ".join(p["title"].strip().lower().split())
        if p_title == target:
            return p
    for p in playlists:
        p_title = " ".join(p["title"].strip().lower().split())
        if target in p_title or p_title in target:
            return p
    return None


def create_playlist(
    title: str,
    description: str = "",
    privacy_status: str = "public",
    access_token: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a new playlist on the authenticated YouTube channel."""
    if not access_token:
        access_token = get_valid_access_token()

    privacy = privacy_status.lower() if privacy_status.lower() in ("public", "unlisted", "private") else "public"
    body = {
        "snippet": {
            "title": title.strip()[:150],
            "description": (description or f"Danh sách phát {title}")[:5000],
            "defaultLanguage": "vi",
        },
        "status": {
            "privacyStatus": privacy,
        },
    }
    req_data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{PLAYLISTS_URL}?part=snippet,status",
        data=req_data,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return {
                "id": data.get("id", ""),
                "title": data.get("snippet", {}).get("title", title),
            }
    except Exception as exc:
        raise YouTubeUploadError(f"Không thể tạo playlist '{title}': {exc}") from exc


def get_or_create_playlist(
    title: str,
    privacy_status: str = "public",
    access_token: Optional[str] = None,
) -> Tuple[str, str]:
    """Return (playlist_id, playlist_title), finding existing or creating new."""
    found = find_playlist_by_title(title, access_token=access_token)
    if found and found.get("id"):
        return str(found["id"]), str(found["title"])
    created = create_playlist(title, privacy_status=privacy_status, access_token=access_token)
    return str(created["id"]), str(created["title"])


def move_playlist_item(
    video_id: str,
    playlist_id: str,
    position: int = 0,
    access_token: Optional[str] = None,
) -> Dict[str, Any]:
    """Move an existing video in a YouTube playlist to a specific position (0 = top of playlist)."""
    if not access_token:
        access_token = get_valid_access_token()

    url = f"{PLAYLIST_ITEMS_URL}?part=snippet&playlistId={playlist_id}&videoId={video_id}&maxResults=1"
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {access_token}"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        items = data.get("items", [])
        if not items:
            return {"success": False, "message": f"Video {video_id} không có trong playlist {playlist_id}."}
        item_id = items[0]["id"]

    body = {
        "id": item_id,
        "snippet": {
            "playlistId": playlist_id,
            "resourceId": {
                "kind": "youtube#video",
                "videoId": video_id,
            },
            "position": int(position),
        },
    }
    put_req = urllib.request.Request(
        f"{PLAYLIST_ITEMS_URL}?part=snippet",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        },
        method="PUT",
    )
    with urllib.request.urlopen(put_req, timeout=15) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        return {
            "success": True,
            "item_id": item_id,
            "playlist_id": playlist_id,
            "video_id": video_id,
            "position": res.get("snippet", {}).get("position", position),
        }


def add_video_to_playlist(
    video_id: str,
    playlist_id: str,
    access_token: Optional[str] = None,
    position: Optional[int] = 0,
) -> Dict[str, Any]:
    """Add a video into a YouTube playlist.

    If position is provided (default 0), the video is inserted at that index
    (0 = top of playlist, pushing existing items down).
    If the video is already in the playlist, moves it to position.
    """
    if not access_token:
        access_token = get_valid_access_token()

    snippet_body: Dict[str, Any] = {
        "playlistId": playlist_id,
        "resourceId": {
            "kind": "youtube#video",
            "videoId": video_id,
        },
    }
    if position is not None:
        snippet_body["position"] = int(position)

    body = {"snippet": snippet_body}
    req_data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{PLAYLIST_ITEMS_URL}?part=snippet",
        data=req_data,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return {
                "success": True,
                "item_id": data.get("id", ""),
                "playlist_id": playlist_id,
                "video_id": video_id,
                "position": data.get("snippet", {}).get("position", position),
            }
    except urllib.error.HTTPError as err:
        err_msg = err.read().decode("utf-8", errors="ignore")
        if "ACCESS_TOKEN_SCOPE_INSUFFICIENT" in err_msg or "insufficient authentication scopes" in err_msg:
            LOGGER.warning("Playlist insertion scope insufficient. Re-authentication needed.")
            return {
                "success": False,
                "reason": "scope_insufficient",
                "message": "Cần cấp quyền quản lý Playlist bằng cách bấm 'Kết nối lại YouTube'.",
            }
        if "videoAlreadyInPlaylist" in err_msg or err.code == 409:
            if position is not None:
                try:
                    move_res = move_playlist_item(video_id, playlist_id, position=position, access_token=access_token)
                    if move_res.get("success"):
                        return move_res
                except Exception as m_exc:
                    LOGGER.debug("Could not move existing video in playlist: %s", m_exc)
            return {
                "success": True,
                "already_in_playlist": True,
                "playlist_id": playlist_id,
                "video_id": video_id,
            }
        LOGGER.warning("Could not add video %s to playlist %s: %s", video_id, playlist_id, err_msg)
        return {
            "success": False,
            "reason": f"HTTP {err.code}",
            "message": err_msg,
        }
    except Exception as exc:
        LOGGER.warning("Could not add video %s to playlist %s: %s", video_id, playlist_id, exc)
        return {
            "success": False,
            "reason": "error",
            "message": str(exc),
        }


def set_video_privacy(
    video_id: str,
    privacy_status: str,
    access_token: Optional[str] = None,
) -> Dict[str, Any]:
    """Update privacy status of an existing YouTube video ('public', 'unlisted', 'private')."""
    if not access_token:
        access_token = get_valid_access_token()

    priv = privacy_status.lower() if privacy_status.lower() in ("public", "unlisted", "private") else "public"

    # Fetch current snippet to avoid losing title / categoryId
    get_url = f"{VIDEOS_URL}?part=snippet,status&id={video_id}"
    req_get = urllib.request.Request(
        get_url,
        headers={"Authorization": f"Bearer {access_token}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req_get, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            items = data.get("items", [])
            if not items:
                return {"success": False, "message": f"Không tìm thấy video ID: {video_id}"}
            video_item = items[0]
    except Exception as exc:
        return {"success": False, "message": f"Không thể lấy thông tin video {video_id}: {exc}"}

    snippet = video_item.get("snippet", {})
    status = video_item.get("status", {})
    status["privacyStatus"] = priv

    body = {
        "id": video_id,
        "snippet": {
            "title": snippet.get("title", ""),
            "description": snippet.get("description", ""),
            "categoryId": snippet.get("categoryId", "25"),
            "tags": snippet.get("tags", []),
        },
        "status": status,
    }
    put_req = urllib.request.Request(
        f"{VIDEOS_URL}?part=snippet,status",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        },
        method="PUT",
    )
    try:
        with urllib.request.urlopen(put_req, timeout=15) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            return {
                "success": True,
                "video_id": video_id,
                "privacy": res.get("status", {}).get("privacyStatus", priv),
            }
    except Exception as exc:
        return {"success": False, "message": f"Không thể đổi quyền riêng tư video {video_id}: {exc}"}


def set_video_thumbnail(
    video_id: str,
    thumbnail_path: str,
    access_token: Optional[str] = None,
) -> Dict[str, Any]:
    """Set a custom thumbnail (JPEG/PNG, < 2 MB) on an uploaded video. Never raises."""
    try:
        path = Path(thumbnail_path)
        if not video_id or not path.is_file():
            return {"success": False, "reason": "missing_file", "message": f"Không có thumbnail: {thumbnail_path}"}
        data = path.read_bytes()
        if len(data) > 2 * 1024 * 1024:
            return {"success": False, "reason": "too_large", "message": "Thumbnail vượt quá 2 MB."}
        if not access_token:
            access_token = get_valid_access_token()
        mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
        req = urllib.request.Request(
            f"{THUMBNAILS_SET_URL}?videoId={urllib.parse.quote(video_id)}&uploadType=media",
            data=data,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": mime,
                "Content-Length": str(len(data)),
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            resp.read()
        return {"success": True, "video_id": video_id}
    except urllib.error.HTTPError as err:
        err_msg = err.read().decode("utf-8", errors="ignore")
        reason = "channel_not_verified" if "forbidden" in err_msg.lower() or err.code == 403 else f"HTTP {err.code}"
        LOGGER.warning("Could not set thumbnail for %s: %s", video_id, err_msg)
        return {"success": False, "reason": reason, "message": err_msg}
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("Could not set thumbnail for %s: %s", video_id, exc)
        return {"success": False, "reason": "error", "message": str(exc)}


def start_oauth_flow(
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
    port: int = 8765,
    timeout: float = 120.0,
) -> Dict[str, Any]:
    """Start local loopback OAuth2 flow to authenticate with Google YouTube."""
    if not client_id or not client_secret:
        c_id, c_secret = get_client_credentials()
        client_id = client_id or c_id
        client_secret = client_secret or c_secret

    if not client_id or not client_secret:
        raise YouTubeAuthError("Vui lòng cung cấp Client ID và Client Secret từ Google Cloud Console.")

    redirect_uri = f"http://127.0.0.1:{port}/"
    scope_str = " ".join(SCOPES)

    auth_params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scope_str,
        "access_type": "offline",
        "prompt": "consent",
    }
    login_url = f"{AUTH_URL}?{urllib.parse.urlencode(auth_params)}"

    auth_code_container: List[str] = []
    error_container: List[str] = []

    class OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            query = urllib.parse.parse_qs(parsed.query)

            if "code" in query:
                auth_code_container.append(query["code"][0])
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                html = """
                <!DOCTYPE html>
                <html>
                <head><title>YouTube Auth</title></head>
                <body style="font-family: sans-serif; text-align: center; padding: 40px; background: #1B1A18; color: #F2EFE9;">
                    <h2 style="color: #4CAF50;">✓ Kết nối kênh YouTube thành công!</h2>
                    <p>Đã nhận được quyền đăng tải. Bạn có thể đóng tab này và quay lại ứng dụng.</p>
                </body>
                </html>
                """
                self.wfile.write(html.encode("utf-8"))
            elif "error" in query:
                error_container.append(query["error"][0])
                self.send_response(400)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(f"Lỗi xác thực: {query['error'][0]}".encode("utf-8"))
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            pass  # Silence stdout logging

    try:
        server = http.server.HTTPServer(("127.0.0.1", port), OAuthCallbackHandler)
        server.timeout = timeout
    except Exception as exc:
        raise YouTubeAuthError(f"Không thể mở cổng xác thực nội bộ ({port}): {exc}") from exc

    # Open browser
    LOGGER.info("Opening browser for YouTube OAuth: %s", login_url)
    webbrowser.open(login_url)

    # Wait for callback
    start_time = time.time()
    while not auth_code_container and not error_container:
        server.handle_request()
        if time.time() - start_time > timeout:
            server.server_close()
            raise YouTubeAuthError("Hết thời gian chờ người dùng đăng nhập xác thực Google (quá 2 phút).")

    server.server_close()

    if error_container:
        raise YouTubeAuthError(f"Người dùng từ chối cấp quyền hoặc Google trả về lỗi: {error_container[0]}")

    auth_code = auth_code_container[0]

    # Exchange code for tokens
    exchange_data = urllib.parse.urlencode({
        "code": auth_code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }).encode("utf-8")

    req = urllib.request.Request(
        TOKEN_URL,
        data=exchange_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            token_resp = json.loads(resp.read().decode("utf-8"))
            token_resp["obtained_at"] = time.time()
            save_client_credentials(client_id, client_secret)
            save_token(token_resp)

            # Retrieve channel title
            ch_info = get_channel_info(token_resp.get("access_token"))
            token_resp["channel_title"] = ch_info.get("title", "")
            save_token(token_resp)
            return token_resp
    except Exception as exc:
        raise YouTubeAuthError(f"Đổi authorization code lấy token thất bại: {exc}") from exc


def sanitize_youtube_metadata(
    title: str,
    description: str = "",
    tags: Optional[List[str]] = None,
) -> Tuple[str, str, List[str]]:
    """Sanitize title, description, and tags to strictly exclude '#haizflow' / 'haizflow'.

    Guarantees no internal branding hashtag or tag leaks into public YouTube video metadata.
    """
    raw_title = title or ""
    clean_title = re.sub(r"#\s*haizflow\b", "", raw_title, flags=re.IGNORECASE)
    clean_title = re.sub(r"[<>]", "", clean_title)
    clean_title = re.sub(r"\s+", " ", clean_title).strip()[:100]

    raw_desc = description or ""
    clean_desc = re.sub(r"#\s*haizflow\b", "", raw_desc, flags=re.IGNORECASE)
    clean_desc = re.sub(r"[<>]", "", clean_desc)
    lines = []
    for line in clean_desc.splitlines():
        cleaned_line = re.sub(r"[ \t]+", " ", line).strip()
        lines.append(cleaned_line)
    clean_desc = "\n".join(lines).strip()[:5000]

    raw_tags = tags or ["tin tức thế giới", "thời sự", "tin tức 24h"]
    clean_tags = []
    total_tag_chars = 0
    for t in raw_tags:
        if not t:
            continue
        cleaned_tag = re.sub(r"[<>]", "", t).replace(",", " ").strip("# ")
        cleaned_tag = re.sub(r"\s+", " ", cleaned_tag).strip()
        if (
            cleaned_tag
            and cleaned_tag.lower() != "haizflow"
            and "haizflow" not in cleaned_tag.lower()
        ):
            # YouTube API total tags length limit is 500 characters
            if total_tag_chars + len(cleaned_tag) + 1 > 480:
                break
            clean_tags.append(cleaned_tag[:100])
            total_tag_chars += len(cleaned_tag) + 1

    if not clean_tags:
        clean_tags = ["tin tức thế giới", "thời sự", "tin tức 24h"]

    return clean_title, clean_desc, clean_tags


def upload_video_to_youtube(
    video_path: str,
    title: str,
    description: str = "",
    tags: Optional[List[str]] = None,
    privacy_status: str = "public",
    category_id: str = "25",  # 25 = News & Politics
    playlist_name: Optional[str] = None,
    playlist_id: Optional[str] = None,
    progress_callback: Optional[Callable[[int, str], None]] = None,
    cancel_event: Optional[threading.Event] = None,
    thumbnail_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Upload video directly to YouTube via Google Resumable Upload protocol.

    Args:
        video_path: Absolute path to local .mp4 video file.
        title: YouTube video title (up to 100 characters).
        description: Description text (up to 5000 characters).
        tags: List of hashtag strings.
        privacy_status: 'public', 'unlisted', or 'private'.
        category_id: YouTube category ('25' = News & Politics).
        progress_callback: Callback receiving (percentage, status_message).
        cancel_event: Event to abort upload.

    Returns:
        Dict containing video_id, url, and full YouTube response.
    """
    v_file = Path(video_path).resolve()
    if not v_file.is_file():
        raise FileNotFoundError(f"Không tìm thấy file video: {video_path}")

    total_bytes = v_file.stat().st_size
    access_token = get_valid_access_token()

    if progress_callback:
        progress_callback(5, "Đang khởi tạo phiên tải lên Google YouTube...")

    # Normalize privacy
    privacy = privacy_status.lower()
    if privacy not in ("public", "unlisted", "private"):
        privacy = "public"

    # Sanitize title, description, and tags - strictly guarantee no #haizflow tag
    title, description, tags = sanitize_youtube_metadata(title, description, tags)

    # Metadata payload
    metadata = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": category_id,
            "defaultLanguage": "vi",
            "defaultAudioLanguage": "vi",
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
            "embeddable": True,
        }
    }

    meta_bytes = json.dumps(metadata, ensure_ascii=False).encode("utf-8")

    # Step 1: Initialize Resumable Upload
    init_url = f"{UPLOAD_URL}?uploadType=resumable&part=snippet,status"
    init_req = urllib.request.Request(
        init_url,
        data=meta_bytes,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "video/mp4",
            "X-Upload-Content-Length": str(total_bytes),
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(init_req, timeout=30) as init_resp:
            session_url = init_resp.headers.get("Location")
            if not session_url:
                raise YouTubeUploadError("Google không trả về Location header để tải video.")
    except urllib.error.HTTPError as err:
        err_msg = err.read().decode("utf-8", errors="ignore")
        if "SERVICE_DISABLED" in err_msg or "has not been used in project" in err_msg:
            act_url = ""
            try:
                d_json = json.loads(err_msg)
                for det in d_json.get("error", {}).get("details", []):
                    if det.get("reason") == "SERVICE_DISABLED":
                        act_url = det.get("metadata", {}).get("activationUrl", "")
                        break
            except Exception:
                pass
            url_hint = f" Vui lòng truy cập liên kết sau và bấm nút 'BẬT' (ENABLE): {act_url}" if act_url else " Vui lòng vào Google Cloud Library và bật YouTube Data API v3."
            raise YouTubeUploadError(
                f"Chưa kích hoạt YouTube Data API v3 trên dự án Google Cloud.{url_hint}"
            ) from err
        raise YouTubeUploadError(f"Khởi tạo tải video thất bại (HTTP {err.code}): {err_msg}") from err
    except Exception as exc:
        raise YouTubeUploadError(f"Khởi tạo phiên upload YouTube thất bại: {exc}") from exc

    LOGGER.info("YouTube upload session initialized: %s", session_url[:80])
    if progress_callback:
        progress_callback(10, "Bắt đầu tải video lên máy chủ YouTube...")

    # Step 2: Upload Video Bytes in Chunks (10MB per chunk)
    CHUNK_SIZE = 10 * 1024 * 1024  # 10MB
    uploaded_bytes = 0

    with open(v_file, "rb") as fp:
        while uploaded_bytes < total_bytes:
            if cancel_event and cancel_event.is_set():
                raise YouTubeUploadError("Đã dừng tiến trình tải video lên YouTube theo yêu cầu.")

            chunk = fp.read(CHUNK_SIZE)
            if not chunk:
                break

            chunk_len = len(chunk)
            chunk_start = uploaded_bytes
            chunk_end = uploaded_bytes + chunk_len - 1

            chunk_req = urllib.request.Request(
                session_url,
                data=chunk,
                headers={
                    "Content-Type": "video/mp4",
                    "Content-Length": str(chunk_len),
                    "Content-Range": f"bytes {chunk_start}-{chunk_end}/{total_bytes}",
                },
                method="PUT",
            )

            try:
                with urllib.request.urlopen(chunk_req, timeout=120) as chunk_resp:
                    uploaded_bytes += chunk_len
                    pct = int(10 + (uploaded_bytes / total_bytes) * 85)
                    mb_done = round(uploaded_bytes / (1024 * 1024), 1)
                    mb_total = round(total_bytes / (1024 * 1024), 1)

                    if progress_callback:
                        progress_callback(pct, f"Đang tải video lên YouTube: {mb_done}/{mb_total} MB ({pct}%)...")

                    # If final chunk, Google responds with 200/201 and video resource
                    if chunk_resp.status in (200, 201):
                        resp_data = json.loads(chunk_resp.read().decode("utf-8"))
                        video_id = resp_data.get("id", "")
                        video_url = f"https://www.youtube.com/watch?v={video_id}"

                        pl_info: Optional[Dict[str, Any]] = None
                        target_pl_id = playlist_id
                        target_pl_name = playlist_name

                        if not target_pl_id and target_pl_name:
                            try:
                                target_pl_id, target_pl_name = get_or_create_playlist(
                                    target_pl_name,
                                    privacy_status=privacy,
                                    access_token=access_token,
                                )
                            except Exception as pl_err:
                                LOGGER.warning("Could not get or create playlist '%s': %s", target_pl_name, pl_err)

                        if target_pl_id and video_id:
                            if progress_callback:
                                progress_callback(98, f"Đang thêm video vào playlist '{target_pl_name or target_pl_id}'...")
                            pl_res = add_video_to_playlist(video_id, target_pl_id, access_token=access_token)
                            pl_info = {
                                "playlist_id": target_pl_id,
                                "playlist_name": target_pl_name or "",
                                "added": pl_res.get("success", False),
                                "message": pl_res.get("message", ""),
                                "scope_insufficient": (pl_res.get("reason") == "scope_insufficient"),
                            }

                        thumb_info: Optional[Dict[str, Any]] = None
                        if thumbnail_path and video_id:
                            if progress_callback:
                                progress_callback(99, "Đang đặt thumbnail tùy chỉnh...")
                            thumb_info = set_video_thumbnail(video_id, thumbnail_path, access_token=access_token)

                        final_msg = f"Đã xuất bản thành công lên YouTube ({privacy}): {video_url}"
                        if pl_info and pl_info["added"]:
                            final_msg += f" (Đã thêm vào playlist '{pl_info['playlist_name']}')"
                        elif pl_info and pl_info.get("scope_insufficient"):
                            final_msg += " (Cần cấp lại quyền để tự động thêm vào playlist)"

                        if progress_callback:
                            progress_callback(100, final_msg)

                        return {
                            "video_id": video_id,
                            "url": video_url,
                            "title": title,
                            "privacy": privacy,
                            "playlist": pl_info,
                            "thumbnail": thumb_info,
                            "data": resp_data,
                        }

            except urllib.error.HTTPError as http_err:
                # 308 Resume Incomplete is expected for intermediate chunks
                if http_err.code == 308:
                    uploaded_bytes += chunk_len
                    pct = int(10 + (uploaded_bytes / total_bytes) * 85)
                    mb_done = round(uploaded_bytes / (1024 * 1024), 1)
                    mb_total = round(total_bytes / (1024 * 1024), 1)
                    if progress_callback:
                        progress_callback(pct, f"Đang truyền dữ liệu lên YouTube: {mb_done}/{mb_total} MB ({pct}%)...")
                    continue
                else:
                    err_body = http_err.read().decode("utf-8", errors="ignore")
                    raise YouTubeUploadError(f"Lỗi khi gửi video lên YouTube (HTTP {http_err.code}): {err_body}") from http_err
            except Exception as exc:
                raise YouTubeUploadError(f"Lỗi kết nối trong khi tải video: {exc}") from exc

    raise YouTubeUploadError("Tải video lên YouTube hoàn tất nhưng không nhận được video ID từ Google.")
