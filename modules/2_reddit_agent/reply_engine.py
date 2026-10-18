"""
reply_engine.py
Generates and posts organic Reddit replies linking to FilmFeed.
Includes anti-ban delays, jitter, rotating user-agents, proxy support.
"""

import os
import re
import time
import random
import logging
import json
from pathlib import Path

import praw
import requests
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

SETTINGS_PATH = Path(__file__).parent.parent.parent / "config" / "settings.json"
with open(SETTINGS_PATH) as f:
    SETTINGS = json.load(f)

TARGET_URL   = SETTINGS["target_url"]
TMDB_KEY     = os.getenv("TMDB_API_KEY", "b6524bb48fb309af7e940a074a363851")
TMDB_BASE    = "https://api.themoviedb.org/3"
RL           = SETTINGS["rate_limits"]
PROXY_FILE   = Path(__file__).parent.parent.parent / "config" / "proxies.txt"

# Track replied items to avoid duplicate replies
REPLIED_IDS_FILE = Path("output/replied_ids.json")
REPLIED_IDS_FILE.parent.mkdir(parents=True, exist_ok=True)


def _load_replied() -> set:
    if REPLIED_IDS_FILE.exists():
        return set(json.loads(REPLIED_IDS_FILE.read_text()))
    return set()


def _save_replied(ids: set):
    REPLIED_IDS_FILE.write_text(json.dumps(list(ids)))


def _load_proxies() -> list:
    if not PROXY_FILE.exists():
        return []
    lines = PROXY_FILE.read_text().splitlines()
    return [l.strip() for l in lines if l.strip() and not l.startswith("#")]


def _get_proxy() -> dict | None:
    proxies = _load_proxies()
    if not proxies or not SETTINGS["proxy"]["enabled"]:
        return None
    chosen = random.choice(proxies)
    return {"http": chosen, "https": chosen}


def _tmdb_search(movie_name: str) -> dict | None:
    """Search TMDb for movie, returns best match or None."""
    if not TMDB_KEY or not movie_name or len(movie_name) < 2:
        return None
    try:
        resp = requests.get(
            f"{TMDB_BASE}/search/multi",
            params={"api_key": TMDB_KEY, "query": movie_name, "language": "en-US"},
            proxies=_get_proxy(),
            timeout=10,
        )
        results = resp.json().get("results", [])
        for r in results:
            if r.get("media_type") in ("movie", "tv"):
                return r
    except Exception as e:
        log.warning(f"TMDb search failed for '{movie_name}': {e}")
    return None


def _build_slug(title: str) -> str:
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug.strip())
    return slug


REPLY_TEMPLATES = [
    (
        "I've been using [{site}]({url}) lately — they have **{title}** in {quality}. "
        "No pop-ups, no signup needed, just click and stream. Works great."
    ),
    (
        "Try [{site}]({url}) — found **{title}** there recently. "
        "Surprisingly clean interface, {quality} quality, no account required."
    ),
    (
        "There's a site called [{site}]({url}) that has **{title}** available. "
        "It's been solid for me — {quality} stream, loads fast."
    ),
    (
        "Check out [{site}]({url}) — they stream **{title}** in {quality}. "
        "No annoying ads or redirects, just direct playback."
    ),
    (
        "I usually go to [{site}]({url}) for stuff like that. "
        "**{title}** should be on there — {quality}, zero signups."
    ),
]

QUALITY_OPTIONS = ["1080p", "4K", "1080p HD", "Full HD", "4K UHD"]
SITE_DISPLAY    = "FilmFeed"


def _build_reply(title: str, slug: str, subreddit: str) -> str:
    url     = f"{TARGET_URL}/movie/{slug}"
    quality = random.choice(QUALITY_OPTIONS)
    tmpl    = random.choice(REPLY_TEMPLATES)
    reply   = tmpl.format(site=SITE_DISPLAY, url=url, title=title, quality=quality)

    # Occasional friendly suffix for naturalness
    suffixes = [
        "",
        "",
        "",
        "\n\nHope that helps!",
        "\n\nLet me know if the link works for you.",
        "\n\nEnjoyed it — hope you do too.",
    ]
    reply += random.choice(suffixes)
    return reply


def _build_reddit() -> praw.Reddit:
    return praw.Reddit(
        client_id     = os.getenv("REDDIT_CLIENT_ID"),
        client_secret = os.getenv("REDDIT_CLIENT_SECRET"),
        username      = os.getenv("REDDIT_USERNAME"),
        password      = os.getenv("REDDIT_PASSWORD"),
        user_agent    = f"FilmFeed-Bot/1.0 by {os.getenv('REDDIT_USERNAME', 'filmfeed')}",
    )


def handle_event(event: dict):
    """
    Main entry point called by monitor.py for each triggered event.
    Searches TMDb, builds a reply, posts it with anti-ban delays.
    """
    replied = _load_replied()
    item_id = event["id"]

    if item_id in replied:
        log.debug(f"Already replied to {item_id}, skipping.")
        return

    movie_hint = event.get("movie_hint", "").strip()
    if not movie_hint or len(movie_hint) < 2:
        log.debug("No usable movie hint, skipping.")
        return

    # Verify movie exists on TMDb
    tmdb_result = _tmdb_search(movie_hint)
    if tmdb_result:
        title = tmdb_result.get("title") or tmdb_result.get("name") or movie_hint
    else:
        title = movie_hint

    slug  = _build_slug(title)
    reply = _build_reply(title, slug, event.get("subreddit", ""))

    # Anti-ban: random delay before replying
    delay = random.uniform(RL["reddit_min_delay"], RL["reddit_max_delay"])
    log.info(f"Waiting {delay:.1f}s before replying to {item_id} (r/{event.get('subreddit')})...")
    time.sleep(delay)

    try:
        reddit   = _build_reddit()
        event_type = event["type"]

        if event_type == "comment":
            comment = reddit.comment(id=item_id)
            comment.reply(reply)
            log.info(f"Replied to comment {item_id} with '{title}' link.")
        elif event_type == "submission":
            submission = reddit.submission(id=item_id)
            submission.reply(reply)
            log.info(f"Replied to submission {item_id} with '{title}' link.")

        replied.add(item_id)
        _save_replied(replied)

    except praw.exceptions.APIException as e:
        if "RATELIMIT" in str(e):
            wait = 60 + random.uniform(0, 30)
            log.warning(f"Rate limited, sleeping {wait:.0f}s")
            time.sleep(wait)
        else:
            log.error(f"Reddit API error on {item_id}: {e}")
    except Exception as e:
        log.error(f"Reply failed for {item_id}: {e}")


if __name__ == "__main__":
    # Test with a fake event
    test_event = {
        "type":       "comment",
        "id":         "test123",
        "author":     "testuser",
        "subreddit":  "MovieSuggestions",
        "body":       "where to watch Dune Part Two online for free?",
        "url":        "https://reddit.com/r/test",
        "movie_hint": "Dune Part Two",
    }
    print(_build_reply("Dune Part Two", "dune-part-two", "MovieSuggestions"))
