"""
tmdb_fetcher.py
Fetches top 10,000 movies + TV series from TMDb with full English metadata.
Saves to output/tmdb_data.json for use by sitemap and Next.js page generators.
"""

import os
import json
import time
import logging
import re
from pathlib import Path
from typing import Generator

import requests
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

TMDB_KEY    = os.getenv("TMDB_API_KEY", "")
TMDB_BASE   = "https://api.themoviedb.org/3"
IMAGE_BASE  = "https://image.tmdb.org/t/p/original"
OUTPUT_FILE = Path("output/tmdb_data.json")
OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

SETTINGS_PATH = Path(__file__).parent.parent.parent / "config" / "settings.json"
with open(SETTINGS_PATH) as f:
    SETTINGS = json.load(f)

FETCH_PAGES = SETTINGS["seo"]["fetch_pages"]  # 50 pages × 20 results = 1000 per endpoint


def _get(endpoint: str, params: dict = {}) -> dict:
    params["api_key"]  = TMDB_KEY
    params["language"] = "en-US"
    resp = requests.get(f"{TMDB_BASE}{endpoint}", params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _slug(title: str) -> str:
    s = title.lower()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"\s+", "-", s.strip())
    return s


def _fetch_pages(endpoint: str, pages: int = FETCH_PAGES) -> list[dict]:
    results = []
    for page in range(1, pages + 1):
        try:
            data  = _get(endpoint, {"page": page})
            items = data.get("results", [])
            results.extend(items)
            if page % 10 == 0:
                log.info(f"  Fetched page {page}/{pages} from {endpoint}")
            time.sleep(0.26)  # Stay under 4 req/s TMDb limit
        except requests.HTTPError as e:
            log.warning(f"HTTP error on page {page}: {e}")
            time.sleep(2)
        except Exception as e:
            log.error(f"Error on page {page}: {e}")
            time.sleep(5)
    return results


def _enrich_movie(item: dict) -> dict:
    """Add extra detail fields to a movie record."""
    return {
        "id":           item.get("id"),
        "type":         "movie",
        "title":        item.get("title", ""),
        "slug":         _slug(item.get("title", "")),
        "overview":     item.get("overview", ""),
        "release_date": item.get("release_date", ""),
        "year":         (item.get("release_date") or "")[:4],
        "rating":       item.get("vote_average", 0),
        "vote_count":   item.get("vote_count", 0),
        "popularity":   item.get("popularity", 0),
        "poster":       f"{IMAGE_BASE}{item['poster_path']}" if item.get("poster_path") else "",
        "backdrop":     f"{IMAGE_BASE}{item['backdrop_path']}" if item.get("backdrop_path") else "",
        "genre_ids":    item.get("genre_ids", []),
        "language":     item.get("original_language", "en"),
    }


def _enrich_tv(item: dict) -> dict:
    return {
        "id":           item.get("id"),
        "type":         "tv",
        "title":        item.get("name", ""),
        "slug":         _slug(item.get("name", "")),
        "overview":     item.get("overview", ""),
        "release_date": item.get("first_air_date", ""),
        "year":         (item.get("first_air_date") or "")[:4],
        "rating":       item.get("vote_average", 0),
        "vote_count":   item.get("vote_count", 0),
        "popularity":   item.get("popularity", 0),
        "poster":       f"{IMAGE_BASE}{item['poster_path']}" if item.get("poster_path") else "",
        "backdrop":     f"{IMAGE_BASE}{item['backdrop_path']}" if item.get("backdrop_path") else "",
        "genre_ids":    item.get("genre_ids", []),
        "language":     item.get("original_language", "en"),
    }


def fetch_all() -> list[dict]:
    log.info("Fetching popular movies...")
    movies_popular  = [_enrich_movie(i) for i in _fetch_pages("/movie/popular")]
    log.info("Fetching top-rated movies...")
    movies_top      = [_enrich_movie(i) for i in _fetch_pages("/movie/top_rated")]
    log.info("Fetching trending movies (week)...")
    movies_trending = [_enrich_movie(i) for i in _fetch_pages("/trending/movie/week", pages=10)]
    log.info("Fetching popular TV series...")
    tv_popular      = [_enrich_tv(i)    for i in _fetch_pages("/tv/popular")]
    log.info("Fetching top-rated TV series...")
    tv_top          = [_enrich_tv(i)    for i in _fetch_pages("/tv/top_rated")]
    log.info("Fetching trending TV (week)...")
    tv_trending     = [_enrich_tv(i)    for i in _fetch_pages("/trending/tv/week", pages=10)]

    all_items = movies_popular + movies_top + movies_trending + tv_popular + tv_top + tv_trending

    # Deduplicate by (id, type)
    seen  = set()
    dedup = []
    for item in all_items:
        key = (item["id"], item["type"])
        if key not in seen:
            seen.add(key)
            dedup.append(item)

    # Sort by popularity descending
    dedup.sort(key=lambda x: x["popularity"], reverse=True)
    log.info(f"Total unique items: {len(dedup)}")
    return dedup[:10000]


def save(items: list[dict]) -> Path:
    OUTPUT_FILE.write_text(json.dumps(items, indent=2, ensure_ascii=False))
    log.info(f"Saved {len(items)} items → {OUTPUT_FILE}")
    return OUTPUT_FILE


def load() -> list[dict]:
    if not OUTPUT_FILE.exists():
        log.info("tmdb_data.json not found, fetching now...")
        items = fetch_all()
        save(items)
        return items
    return json.loads(OUTPUT_FILE.read_text())


if __name__ == "__main__":
    items = fetch_all()
    save(items)
    print(f"Done. {len(items)} items saved to {OUTPUT_FILE}")
