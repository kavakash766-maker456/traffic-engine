"""
run_shorts.py
CLI orchestrator for the full shorts pipeline.
Usage:
  python run_shorts.py --movie "Dune Part Two"
  python run_shorts.py --trending --count 5
"""

import argparse
import logging
import sys
import time
import json
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# Local imports
sys.path.insert(0, str(Path(__file__).parent))
from clip_extractor import download_clip, download_trending_clips
from video_editor   import edit_clip
from uploader_youtube import upload_short as yt_upload
from uploader_tiktok  import upload_short as tt_upload

SETTINGS_PATH = Path(__file__).parent.parent.parent / "config" / "settings.json"
with open(SETTINGS_PATH) as f:
    SETTINGS = json.load(f)

TMDB_API_KEY  = __import__("os").getenv("TMDB_API_KEY", "")
TMDB_BASE     = "https://api.themoviedb.org/3"
TARGET_URL    = SETTINGS["target_url"]


def _get_movie_meta(movie_name: str) -> dict:
    """Fetch genre + slug from TMDb."""
    try:
        resp = requests.get(
            f"{TMDB_BASE}/search/movie",
            params={"api_key": TMDB_API_KEY, "query": movie_name, "language": "en-US"},
            timeout=10,
        )
        results = resp.json().get("results", [])
        if results:
            movie   = results[0]
            genres  = movie.get("genre_ids", [])
            title   = movie.get("title", movie_name)
            slug    = title.lower().replace(" ", "-").replace(":", "").replace("'", "")
            genre   = "Movie"
            return {"title": title, "slug": slug, "genre": genre, "id": movie.get("id")}
    except Exception as e:
        log.warning(f"TMDb lookup failed: {e}")
    slug = movie_name.lower().replace(" ", "-")
    return {"title": movie_name, "slug": slug, "genre": "Movie", "id": None}


def process_movie(movie_name: str, upload_yt: bool = True, upload_tt: bool = True) -> dict:
    """Full pipeline for one movie. Returns result dict."""
    log.info(f"━━━ Processing: {movie_name} ━━━")
    meta = _get_movie_meta(movie_name)

    # Step 1: Download clip
    clip_path = download_clip(meta["title"])
    if not clip_path:
        return {"movie": movie_name, "status": "failed", "reason": "clip download failed"}

    # Step 2: Edit into short
    try:
        short_path = edit_clip(clip_path, meta["title"])
    except Exception as e:
        log.error(f"Edit failed: {e}")
        return {"movie": movie_name, "status": "failed", "reason": f"edit error: {e}"}

    result = {"movie": movie_name, "slug": meta["slug"], "short": str(short_path), "uploads": {}}

    # Step 3: Upload YouTube
    if upload_yt:
        try:
            vid_id = yt_upload(short_path, meta["title"], meta["genre"], meta["slug"])
            result["uploads"]["youtube"] = vid_id or "failed"
        except Exception as e:
            log.error(f"YouTube upload failed: {e}")
            result["uploads"]["youtube"] = "error"

    # Step 4: Upload TikTok
    if upload_tt:
        try:
            ok = tt_upload(short_path, meta["title"], meta["slug"])
            result["uploads"]["tiktok"] = "success" if ok else "failed"
        except Exception as e:
            log.error(f"TikTok upload failed: {e}")
            result["uploads"]["tiktok"] = "error"

    result["status"] = "done"
    log.info(f"Finished: {movie_name} → {result['uploads']}")
    return result


def run_trending(count: int = 5, upload_yt: bool = True, upload_tt: bool = True):
    """Process top N trending movies."""
    items   = download_trending_clips(count)
    results = []
    for item in items:
        if not item["path"]:
            log.warning(f"Skipping {item['name']} — no clip.")
            continue
        r = process_movie(item["name"], upload_yt, upload_tt)
        results.append(r)
        # Rate limit between uploads
        wait = SETTINGS["rate_limits"]["youtube_upload_interval"]
        log.info(f"Waiting {wait}s before next upload...")
        time.sleep(wait)
    return results


def main():
    parser = argparse.ArgumentParser(description="FilmFeed Shorts Pipeline")
    group  = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--movie",    type=str, help="Movie name")
    group.add_argument("--trending", action="store_true", help="Process trending movies")
    parser.add_argument("--count",   type=int, default=5, help="Number of trending movies")
    parser.add_argument("--no-yt",   action="store_true", help="Skip YouTube upload")
    parser.add_argument("--no-tt",   action="store_true", help="Skip TikTok upload")
    args = parser.parse_args()

    yt = not args.no_yt
    tt = not args.no_tt

    if args.movie:
        result = process_movie(args.movie, yt, tt)
        print(json.dumps(result, indent=2))
    elif args.trending:
        results = run_trending(args.count, yt, tt)
        print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
