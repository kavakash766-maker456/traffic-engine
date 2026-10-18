"""
generate_sitemap.py
Generates dynamic sitemap.xml files split into chunks of ≤45,000 URLs.
Also generates a sitemap index file.
Pings Google and Bing indexing APIs after generation.
"""

import os
import json
import logging
import math
import datetime
import requests
from pathlib import Path
from xml.etree import ElementTree as ET

from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

SETTINGS_PATH = Path(__file__).parent.parent.parent / "config" / "settings.json"
with open(SETTINGS_PATH) as f:
    SETTINGS = json.load(f)

BASE_URL     = SETTINGS["seo"]["sitemap_base_url"]
CHUNK_SIZE   = SETTINGS["seo"]["movies_per_sitemap"]
OUTPUT_DIR   = Path("output/sitemaps")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

GOOGLE_INDEXING_KEY = os.getenv("GOOGLE_INDEXING_API_KEY", "")
BING_INDEXING_KEY   = os.getenv("BING_INDEXING_API_KEY", "")

NS = "http://www.sitemaps.org/schemas/sitemap/0.9"


def _url_element(parent: ET.Element, loc: str, lastmod: str, changefreq: str = "weekly", priority: str = "0.8"):
    url = ET.SubElement(parent, "url")
    ET.SubElement(url, "loc").text        = loc
    ET.SubElement(url, "lastmod").text    = lastmod
    ET.SubElement(url, "changefreq").text = changefreq
    ET.SubElement(url, "priority").text   = priority


def generate_sitemaps(items: list[dict]) -> list[Path]:
    """Split items into chunks and write sitemap XML files. Returns list of file paths."""
    today    = datetime.date.today().isoformat()
    chunks   = math.ceil(len(items) / CHUNK_SIZE)
    paths    = []

    for i in range(chunks):
        chunk       = items[i * CHUNK_SIZE: (i + 1) * CHUNK_SIZE]
        urlset      = ET.Element("urlset", xmlns=NS)
        for item in chunk:
            media_type = "movie" if item["type"] == "movie" else "tv"
            loc        = f"{BASE_URL}/{media_type}/{item['slug']}"
            # Newer releases get higher changefreq
            year       = int(item.get("year") or 2000)
            freq       = "daily" if year >= datetime.date.today().year - 1 else "weekly"
            priority   = "0.9" if item.get("popularity", 0) > 50 else "0.7"
            _url_element(urlset, loc, today, freq, priority)

        # Add static pages in first chunk
        if i == 0:
            for static in ["", "/trending", "/genres", "/top-rated", "/new-releases"]:
                _url_element(urlset, f"{BASE_URL}{static}", today, "daily", "1.0")

        tree     = ET.ElementTree(urlset)
        ET.indent(tree, space="  ")
        out_path = OUTPUT_DIR / f"sitemap-{i+1}.xml"
        tree.write(str(out_path), xml_declaration=True, encoding="utf-8")
        paths.append(out_path)
        log.info(f"Written {out_path} ({len(chunk)} URLs)")

    return paths


def generate_index(sitemap_paths: list[Path]) -> Path:
    """Generate sitemap index file pointing to all chunk sitemaps."""
    today    = datetime.date.today().isoformat()
    index    = ET.Element("sitemapindex", xmlns=NS)
    for path in sitemap_paths:
        sitemap = ET.SubElement(index, "sitemap")
        ET.SubElement(sitemap, "loc").text     = f"{BASE_URL}/sitemaps/{path.name}"
        ET.SubElement(sitemap, "lastmod").text = today

    tree = ET.ElementTree(index)
    ET.indent(tree, space="  ")
    idx_path = OUTPUT_DIR / "sitemap_index.xml"
    tree.write(str(idx_path), xml_declaration=True, encoding="utf-8")
    log.info(f"Sitemap index written: {idx_path}")
    return idx_path


def ping_google(sitemap_url: str):
    """Ping Google Search Console indexing API."""
    if not GOOGLE_INDEXING_KEY:
        log.info("No Google indexing key set, skipping ping.")
        return
    try:
        resp = requests.get(
            "https://www.google.com/ping",
            params={"sitemap": sitemap_url},
            timeout=15,
        )
        log.info(f"Google ping: {resp.status_code}")
    except Exception as e:
        log.warning(f"Google ping failed: {e}")


def ping_bing(sitemap_url: str):
    """Ping Bing IndexNow API."""
    if not BING_INDEXING_KEY:
        log.info("No Bing key set, skipping ping.")
        return
    try:
        resp = requests.get(
            "https://www.bing.com/ping",
            params={"sitemap": sitemap_url},
            timeout=15,
        )
        log.info(f"Bing ping: {resp.status_code}")
    except Exception as e:
        log.warning(f"Bing ping failed: {e}")


def run():
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from tmdb_fetcher import load

    items = load()
    log.info(f"Generating sitemaps for {len(items)} items...")

    sitemap_paths = generate_sitemaps(items)
    index_path    = generate_index(sitemap_paths)

    sitemap_index_url = f"{BASE_URL}/sitemaps/sitemap_index.xml"
    ping_google(sitemap_index_url)
    ping_bing(sitemap_index_url)

    log.info(f"All done. {len(sitemap_paths)} sitemap files + index.")
    return index_path


if __name__ == "__main__":
    run()
