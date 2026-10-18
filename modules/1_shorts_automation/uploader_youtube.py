"""
uploader_youtube.py
Uploads processed shorts to YouTube via YouTube Data API v3.
Handles OAuth2 token refresh automatically.
"""

import os
import json
import logging
import time
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

SCOPES        = ["https://www.googleapis.com/auth/youtube.upload"]
TOKEN_FILE    = Path("config/youtube_token.json")
CLIENT_SECRET = Path(os.getenv("YOUTUBE_CLIENT_SECRET_PATH", "config/youtube_client_secret.json"))

SETTINGS_PATH = Path(__file__).parent.parent.parent / "config" / "settings.json"
with open(SETTINGS_PATH) as f:
    SETTINGS = json.load(f)

YT_SETTINGS   = SETTINGS["youtube_shorts"]
TARGET_URL    = SETTINGS["target_url"]


def _get_credentials() -> Credentials:
    """Load or refresh OAuth2 credentials."""
    creds = None

    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            log.info("Refreshing YouTube OAuth token...")
            creds.refresh(Request())
        else:
            log.info("Starting YouTube OAuth flow...")
            flow  = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(creds.to_json())
        log.info("Token saved.")

    return creds


def _build_service():
    creds = _get_credentials()
    return build("youtube", "v3", credentials=creds)


def upload_short(
    video_path: Path,
    movie_name: str,
    genre: str = "Movie",
    movie_slug: str = "",
    thumbnail_path: Path | None = None,
) -> str | None:
    """
    Upload video as YouTube Short.
    Returns the video ID or None on failure.
    """
    movie_url = f"{TARGET_URL}/movie/{movie_slug}" if movie_slug else TARGET_URL
    title       = YT_SETTINGS["title_template"].format(movie_name=movie_name)[:100]
    description = YT_SETTINGS["description_template"].format(
        movie_name=movie_name,
        url=movie_url,
        genre=genre.replace(" ", ""),
    )
    tags = YT_SETTINGS["tags"] + [movie_name, genre]

    body = {
        "snippet": {
            "title":       title,
            "description": description,
            "tags":        tags[:500],
            "categoryId":  YT_SETTINGS["category_id"],
        },
        "status": {
            "privacyStatus":          YT_SETTINGS["privacy_status"],
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(
        str(video_path),
        mimetype="video/mp4",
        resumable=True,
        chunksize=1024 * 1024 * 5,  # 5MB chunks
    )

    service  = _build_service()
    request  = service.videos().insert(part="snippet,status", body=body, media_body=media)

    log.info(f"Uploading '{title}' to YouTube...")
    response = None
    retry    = 0
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                pct = int(status.progress() * 100)
                log.info(f"Upload progress: {pct}%")
        except Exception as e:
            if retry < 5:
                wait = 2 ** retry
                log.warning(f"Upload error, retrying in {wait}s: {e}")
                time.sleep(wait)
                retry += 1
            else:
                log.error(f"Upload failed after {retry} retries: {e}")
                return None

    video_id = response.get("id")
    log.info(f"Uploaded successfully: https://youtu.be/{video_id}")

    # Set thumbnail if provided
    if thumbnail_path and thumbnail_path.exists() and video_id:
        try:
            service.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(str(thumbnail_path), mimetype="image/jpeg"),
            ).execute()
            log.info("Thumbnail set.")
        except Exception as e:
            log.warning(f"Thumbnail upload failed: {e}")

    return video_id


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--video",  required=True)
    parser.add_argument("--name",   required=True)
    parser.add_argument("--genre",  default="Movie")
    parser.add_argument("--slug",   default="")
    args = parser.parse_args()
    vid = upload_short(Path(args.video), args.name, args.genre, args.slug)
    print(f"Video ID: {vid}")
