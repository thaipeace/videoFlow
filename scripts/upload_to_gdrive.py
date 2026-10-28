#!/usr/bin/env python3
"""Google Drive Webhook Uploader for HaizFlow / videoFlow.

Uploads editorial scripts, Proof-of-Work texts, or manifests to Google Drive
via the Google Apps Script Webhook. Zero external dependencies (uses standard library urllib).
Features strict deduplication tracking using sentinel files (.gdrive_uploaded) to prevent
duplicate uploads.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("gdrive_uploader")

DEFAULT_WEBHOOK_URL = (
    "https://script.google.com/macros/s/AKfycbzVrVvGB0HAFhO9GgH-g5EP_iPfoFjZlNdhX_tXhvu-bfeznog8WabsX8nYj2SwbvOd/exec"
)


def get_webhook_url(custom_url: Optional[str] = None) -> str:
    """Resolve active Google Apps Script Webhook URL."""
    if custom_url and custom_url.strip():
        return custom_url.strip()
    env_url = os.environ.get("GDRIVE_WEBHOOK_URL", "").strip()
    if env_url:
        return env_url
    return DEFAULT_WEBHOOK_URL


def get_sentinel_path(file_path: Path) -> Path:
    """Return the companion sentinel path indicating successful upload."""
    return file_path.with_suffix(file_path.suffix + ".gdrive_uploaded")


def upload_text_file(
    file_path: Path | str,
    webhook_url: Optional[str] = None,
    custom_filename: Optional[str] = None,
    max_retries: int = 2,
    force: bool = False,
) -> Optional[Dict[str, Any]]:
    """Upload a single text file to Google Drive via Apps Script Webhook with deduplication."""
    p = Path(file_path).resolve()
    if not p.is_file():
        logger.error("File does not exist: %s", p)
        return None

    filename = custom_filename or p.name
    sentinel = get_sentinel_path(p)

    # Deduplication check
    if not force and sentinel.is_file():
        logger.info("⏩ Script '%s' was already uploaded to Google Drive. Skipping duplicate.", filename)
        try:
            return json.loads(sentinel.read_text(encoding="utf-8"))
        except Exception:
            return {"status": "skipped", "fileId": "cached", "filename": filename}

    try:
        content = p.read_text(encoding="utf-8")
    except Exception as exc:
        logger.error("Could not read file %s: %s", p, exc)
        return None

    url = get_webhook_url(webhook_url)
    payload_bytes = json.dumps({"filename": filename, "content": content}, ensure_ascii=False).encode("utf-8")

    logger.info("Uploading '%s' (%d bytes) to Google Drive...", filename, len(payload_bytes))

    for attempt in range(1, max_retries + 1):
        req = urllib.request.Request(
            url,
            data=payload_bytes,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                resp_text = resp.read().decode("utf-8")
                try:
                    data = json.loads(resp_text)
                except Exception:
                    data = {"raw": resp_text}

                if data.get("status") == "success":
                    file_id = data.get("fileId", "unknown")
                    logger.info("✅ SUCCESS: Uploaded '%s' -> Google Drive (File ID: %s)", filename, file_id)
                    try:
                        sentinel.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
                    except Exception as sent_err:
                        logger.warning("Could not write upload sentinel: %s", sent_err)
                    return data
                else:
                    logger.warning("Attempt %d returned status: %s", attempt, data)
        except urllib.error.HTTPError as http_err:
            logger.warning("Attempt %d HTTP Error: %s", attempt, http_err)
        except Exception as exc:
            logger.warning("Attempt %d Network/Timeout Error: %s", attempt, exc)

        if attempt < max_retries:
            time.sleep(2.0 * attempt)

    logger.error("❌ FAILED to upload '%s' after %d attempts.", filename, max_retries)
    return None


def upload_directory_files(
    directory: Path | str,
    pattern: str = "*.txt",
    webhook_url: Optional[str] = None,
    limit: Optional[int] = 1,
    force: bool = False,
) -> List[Dict[str, Any]]:
    """Upload matching text files from a directory, sorted newest first, skipping already uploaded files."""
    d = Path(directory).resolve()
    if not d.is_dir():
        logger.warning("Directory not found: %s", d)
        return []

    # Find candidate files
    all_files = sorted(d.glob(pattern), key=lambda f: f.stat().st_mtime, reverse=True)
    if not force:
        pending_files = [f for f in all_files if not get_sentinel_path(f).is_file()]
    else:
        pending_files = all_files

    if not pending_files:
        logger.info("All matching file(s) in %s have already been uploaded to Google Drive. Skipping.", d)
        return []

    if limit is not None and limit > 0:
        pending_files = pending_files[:limit]

    logger.info("Found %d pending file(s) in %s to upload (out of %d total)", len(pending_files), d, len(all_files))
    uploaded = []
    for f in pending_files:
        res = upload_text_file(f, webhook_url=webhook_url, force=force)
        if res and res.get("status") == "success":
            uploaded.append(res)
        time.sleep(0.5)

    return uploaded


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload files to Google Drive via Webhook with Deduplication")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", type=str, help="Upload a specific text file.")
    group.add_argument("--dir", type=str, help="Upload files from a directory.")
    parser.add_argument("--pattern", type=str, default="*.txt", help="Filename pattern for --dir (default: *.txt)")
    parser.add_argument("--limit", type=int, default=1, help="Maximum number of new files to upload from --dir (default: 1).")
    parser.add_argument("--url", type=str, default=None, help="Custom Webhook URL.")
    parser.add_argument("--force", action="store_true", help="Force re-upload even if sentinel file exists.")

    args = parser.parse_args()

    if args.file:
        res = upload_text_file(args.file, webhook_url=args.url, force=args.force)
        return 0 if res else 1
    elif args.dir:
        res_list = upload_directory_files(args.dir, pattern=args.pattern, webhook_url=args.url, limit=args.limit, force=args.force)
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
