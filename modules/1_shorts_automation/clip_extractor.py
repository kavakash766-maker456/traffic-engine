"""
clip_extractor.py
Fetches trending trailers/clips from YouTube using yt-dlp.
Supports single movie fetch and auto-trending discovery via TMDb.
"""

import os
import json
import logging
import subprocess
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TMDB_BASE    = "https://api.themoviedb.org/3"
OUTPUT_DIR   = Path("output/clips")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SETTINGS_PATH = Path(__file__).parent.parent.parent / "config" / "settings.json"
with open(SETTINGS_PATH) as f:
    SETTINGS = json.load(f)


def get_trending_movies(count: int = 10) -> list[dict]:
    """Fetch trending movies from TMDb."""
    url = f"{TMDB_BASE}/trending/movie/day"
    params = {"api_key": TMDB_API_KEY, "language": "en-US"}
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    results = resp.json().get("results", [])[:count]
    log.info(f"Fetched {len(results)} trending movies from TMDb.")
    return results


def search_youtube_trailer(movie_name: str) -> str | None:
    """Search YouTube for the official trailer URL using yt-dlp."""
    query = f"{movie_name} official trailer 1080p"
    cmd = [
        "yt-dlp",
        f"ytsearch1:{query}",
        "--get-url",
        "--no-playlist",
        "-f", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        url = result.stdout.strip().split("\n")[0]
        if url.startswith("http"):
            log.info(f"Found trailer URL for '{movie_name}'")
            return url
    except Exception as e:
        log.warning(f"yt-dlp search failed for '{movie_name}': {e}")
    return None


def download_clip(movie_name: str, url: str | None = None) -> Path | None:
    """
    Download a trailer/clip for a given movie name.
    If url is None, searches YouTube automatically.
    Returns path to downloaded file.
    """
    safe_name = "".join(c if c.isalnum() or c in " _-" else "" for c in movie_name).strip().replace(" ", "_")
    out_path   = OUTPUT_DIR / f"{safe_name}.mp4"

    if out_path.exists():
        log.info(f"Clip already exists: {out_path}")
        return out_path

    if url is None:
        url = search_youtube_trailer(movie_name)

    if not url:
        log.error(f"No URL found for '{movie_name}'")
        return None

    cmd = [
        "yt-dlp",
        url,
        "-o", str(out_path),
        "-f", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best",
        "--merge-output-format", "mp4",
        "--no-playlist",
        "--quiet",
        "--progress",
    ]

    log.info(f"Downloading clip for '{movie_name}' → {out_path}")
    result = subprocess.run(cmd, timeout=300)

    if result.returncode == 0 and out_path.exists():
        log.info(f"Download complete: {out_path}")
        return out_path

    log.error(f"Download failed for '{movie_name}'")
    return None


def download_trending_clips(count: int = 5) -> list[dict]:
    """Download clips for the top N trending movies. Returns list of {name, path, tmdb_data}."""
    movies  = get_trending_movies(count)
    results = []
    for movie in movies:
        name = movie.get("title") or movie.get("name", "Unknown")
        path = download_clip(name)
        results.append({"name": name, "path": path, "tmdb_data": movie})
    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--movie", type=str, help="Movie name to download")
    parser.add_argument("--trending", action="store_true", help="Download trending movies")
    parser.add_argument("--count", type=int, default=5)
    args = parser.parse_args()

    if args.movie:
        path = download_clip(args.movie)
        print(f"Downloaded: {path}")
    elif args.trending:
        items = download_trending_clips(args.count)
        for item in items:
            print(f"{item['name']}: {item['path']}")
    else:
        parser.print_help()
