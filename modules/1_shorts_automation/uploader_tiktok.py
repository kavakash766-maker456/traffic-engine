"""
uploader_tiktok.py
Uploads processed shorts to TikTok via session-cookie automation.
Uses TikTok Content Posting API where available, falls back to session auth.
"""

import os
import json
import time
import logging
import random
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

SETTINGS_PATH = Path(__file__).parent.parent.parent / "config" / "settings.json"
with open(SETTINGS_PATH) as f:
    SETTINGS = json.load(f)

TARGET_URL      = SETTINGS["target_url"]
TIKTOK_SESSION  = os.getenv("TIKTOK_SESSION_COOKIE", "")
TIKTOK_API_KEY  = os.getenv("TIKTOK_API_KEY", "")
TIKTOK_API_SECRET = os.getenv("TIKTOK_API_SECRET", "")

# TikTok Content Posting API endpoint
TIKTOK_UPLOAD_INIT = "https://open.tiktokapis.com/v2/post/publish/video/init/"
TIKTOK_UPLOAD_COMPLETE = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"

USER_AGENTS = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/116.0.5845.103 Mobile/15E148 Safari/604.1",
]


def _get_headers(access_token: str = "") -> dict:
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json",
        "Content-Type": "application/json; charset=UTF-8",
    }
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    return headers


def _build_caption(movie_name: str, movie_slug: str = "") -> str:
    movie_url = f"{TARGET_URL}/movie/{movie_slug}" if movie_slug else TARGET_URL
    return (
        f"🎬 {movie_name} — Watch FREE in 4K!\n"
        f"👉 {movie_url}\n\n"
        f"No ads. No signup. Instant stream.\n\n"
        f"#FreeMovies #4KStream #MovieNight #Shorts #{movie_name.replace(' ', '')} #WatchOnline"
    )


def upload_via_api(
    video_path: Path,
    movie_name: str,
    movie_slug: str = "",
    access_token: str = "",
) -> bool:
    """
    Upload using TikTok Content Posting API v2.
    Requires a valid OAuth access token with video.publish scope.
    """
    if not access_token:
        access_token = os.getenv("TIKTOK_ACCESS_TOKEN", "")
    if not access_token:
        log.warning("No TikTok access token — skipping API upload.")
        return False

    caption   = _build_caption(movie_name, movie_slug)
    file_size = video_path.stat().st_size

    # Step 1: Initialize upload
    init_payload = {
        "post_info": {
            "title":         caption[:2200],
            "privacy_level": "PUBLIC_TO_EVERYONE",
            "disable_duet":  False,
            "disable_stitch": False,
            "disable_comment": False,
            "video_cover_timestamp_ms": 1000,
        },
        "source_info": {
            "source":     "FILE_UPLOAD",
            "video_size": file_size,
            "chunk_size": min(file_size, 10 * 1024 * 1024),
            "total_chunk_count": max(1, file_size // (10 * 1024 * 1024) + 1),
        },
    }

    headers = _get_headers(access_token)
    log.info("Initializing TikTok API upload...")
    resp = requests.post(TIKTOK_UPLOAD_INIT, json=init_payload, headers=headers, timeout=30)

    if resp.status_code != 200:
        log.error(f"TikTok init failed: {resp.status_code} {resp.text}")
        return False

    data        = resp.json().get("data", {})
    publish_id  = data.get("publish_id")
    upload_url  = data.get("upload_url")

    if not upload_url:
        log.error("No upload URL returned from TikTok API.")
        return False

    # Step 2: Upload video bytes
    log.info(f"Uploading video to TikTok upload URL...")
    chunk_size = min(file_size, 10 * 1024 * 1024)
    with open(video_path, "rb") as f:
        chunk_index = 0
        offset      = 0
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            chunk_end = offset + len(chunk) - 1
            upload_headers = {
                "Content-Type":  "video/mp4",
                "Content-Range": f"bytes {offset}-{chunk_end}/{file_size}",
                "Content-Length": str(len(chunk)),
            }
            upload_resp = requests.put(upload_url, data=chunk, headers=upload_headers, timeout=120)
            if upload_resp.status_code not in (200, 206):
                log.error(f"Chunk upload failed: {upload_resp.status_code}")
                return False
            offset      += len(chunk)
            chunk_index += 1
            log.info(f"Uploaded chunk {chunk_index}, offset {offset}/{file_size}")

    log.info(f"TikTok upload complete. Publish ID: {publish_id}")
    return True


def upload_via_session(
    video_path: Path,
    movie_name: str,
    movie_slug: str = "",
) -> bool:
    """
    Fallback: session-cookie based upload for unattended posting.
    Uses stored session cookie from TIKTOK_SESSION_COOKIE env var.
    """
    if not TIKTOK_SESSION:
        log.warning("No TikTok session cookie configured.")
        return False

    caption = _build_caption(movie_name, movie_slug)
    session = requests.Session()
    session.headers.update({
        "User-Agent": random.choice(USER_AGENTS),
        "Referer":    "https://www.tiktok.com/",
        "Cookie":     f"sessionid={TIKTOK_SESSION}",
    })

    # Fetch upload signature
    sign_url = "https://www.tiktok.com/api/upload/v1/init/"
    sign_resp = session.post(sign_url, json={
        "video_size":  video_path.stat().st_size,
        "chunk_size":  5 * 1024 * 1024,
        "total_chunk": 1,
    }, timeout=20)

    if sign_resp.status_code != 200:
        log.error(f"Session upload init failed: {sign_resp.status_code}")
        return False

    sign_data   = sign_resp.json()
    upload_id   = sign_data.get("upload_id")
    upload_host = sign_data.get("upload_url", "https://www.tiktok.com/api/upload/v1/chunk/")

    with open(video_path, "rb") as f:
        video_bytes = f.read()

    upload_resp = session.post(
        upload_host,
        files={"video": ("short.mp4", video_bytes, "video/mp4")},
        data={"upload_id": upload_id, "chunk_idx": 0},
        timeout=180,
    )

    if upload_resp.status_code != 200:
        log.error(f"Session video upload failed: {upload_resp.status_code}")
        return False

    # Publish
    pub_resp = session.post(
        "https://www.tiktok.com/api/upload/v1/commit/",
        json={
            "upload_id": upload_id,
            "text":      caption[:2200],
            "privacy":   0,  # public
        },
        timeout=30,
    )

    if pub_resp.status_code == 200:
        log.info("TikTok session upload and publish successful.")
        return True

    log.error(f"TikTok publish failed: {pub_resp.status_code} {pub_resp.text}")
    return False


def upload_short(
    video_path: Path,
    movie_name: str,
    movie_slug: str = "",
    access_token: str = "",
) -> bool:
    """Main entry — tries API first, falls back to session."""
    jitter = random.uniform(SETTINGS["rate_limits"]["tiktok_upload_interval"] * 0.1, 3)
    time.sleep(jitter)

    success = upload_via_api(video_path, movie_name, movie_slug, access_token)
    if not success:
        log.info("API upload failed, trying session fallback...")
        success = upload_via_session(video_path, movie_name, movie_slug)
    return success


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True)
    parser.add_argument("--name",  required=True)
    parser.add_argument("--slug",  default="")
    args = parser.parse_args()
    ok = upload_short(Path(args.video), args.name, args.slug)
    print("Success" if ok else "Failed")
