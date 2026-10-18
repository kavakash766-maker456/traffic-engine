"""
monitor.py
Streams Reddit submissions and comments across target subreddits.
Fires callback when a trigger phrase is detected.
"""

import os
import re
import time
import logging
import json
from pathlib import Path
from typing import Callable

import praw
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

SETTINGS_PATH = Path(__file__).parent.parent.parent / "config" / "settings.json"
with open(SETTINGS_PATH) as f:
    SETTINGS = json.load(f)

SUBREDDITS = SETTINGS["reddit_subreddits"]
TRIGGERS   = SETTINGS["reddit_triggers"]

# Compile trigger patterns once
TRIGGER_PATTERNS = [re.compile(t, re.IGNORECASE) for t in TRIGGERS]


def _build_reddit() -> praw.Reddit:
    return praw.Reddit(
        client_id     = os.getenv("REDDIT_CLIENT_ID"),
        client_secret = os.getenv("REDDIT_CLIENT_SECRET"),
        username      = os.getenv("REDDIT_USERNAME"),
        password      = os.getenv("REDDIT_PASSWORD"),
        user_agent    = f"FilmFeed-Bot/1.0 by {os.getenv('REDDIT_USERNAME', 'filmfeed')}",
    )


def _is_triggered(text: str) -> tuple[bool, str]:
    """Returns (matched, movie_name_extracted)."""
    for pattern in TRIGGER_PATTERNS:
        match = pattern.search(text)
        if match:
            # Try to extract what they're looking for
            remainder = text[match.end():].strip()
            # Take first 60 chars as likely movie name
            movie_hint = remainder[:60].split("\n")[0].strip(" ?.,!")
            return True, movie_hint
    return False, ""


def stream_subreddits(on_match: Callable[[dict], None], max_retries: int = 10):
    """
    Continuously stream comments and submissions across all target subreddits.
    Calls on_match(event_dict) whenever a trigger is detected.
    event_dict keys: type, id, author, subreddit, title, body, url, movie_hint
    """
    reddit     = _build_reddit()
    sub_string = "+".join(SUBREDDITS)
    subreddit  = reddit.subreddit(sub_string)

    log.info(f"Streaming r/{sub_string} ...")

    retries = 0
    while True:
        try:
            # Stream comments
            for comment in subreddit.stream.comments(skip_existing=True, pause_after=5):
                if comment is None:
                    break
                triggered, movie_hint = _is_triggered(comment.body)
                if triggered:
                    on_match({
                        "type":       "comment",
                        "id":         comment.id,
                        "fullname":   comment.name,
                        "author":     str(comment.author),
                        "subreddit":  str(comment.subreddit),
                        "title":      comment.submission.title if hasattr(comment, "submission") else "",
                        "body":       comment.body,
                        "url":        f"https://reddit.com{comment.permalink}",
                        "movie_hint": movie_hint,
                        "created_utc": comment.created_utc,
                    })

            # Stream new submissions
            for submission in subreddit.stream.submissions(skip_existing=True, pause_after=5):
                if submission is None:
                    break
                text = f"{submission.title} {submission.selftext}"
                triggered, movie_hint = _is_triggered(text)
                if triggered:
                    on_match({
                        "type":       "submission",
                        "id":         submission.id,
                        "fullname":   submission.name,
                        "author":     str(submission.author),
                        "subreddit":  str(submission.subreddit),
                        "title":      submission.title,
                        "body":       submission.selftext,
                        "url":        submission.url,
                        "permalink":  f"https://reddit.com{submission.permalink}",
                        "movie_hint": movie_hint,
                        "created_utc": submission.created_utc,
                    })

            retries = 0

        except praw.exceptions.PRAWException as e:
            log.warning(f"PRAW error: {e}")
            wait = min(60, 5 * (2 ** retries))
            log.info(f"Reconnecting in {wait}s...")
            time.sleep(wait)
            retries = min(retries + 1, max_retries)
            reddit  = _build_reddit()

        except Exception as e:
            log.error(f"Stream error: {e}")
            time.sleep(30)


if __name__ == "__main__":
    def debug_handler(event):
        log.info(f"TRIGGERED [{event['type']}] r/{event['subreddit']} | hint: '{event['movie_hint']}'")
        log.info(f"  URL: {event.get('url', event.get('permalink', ''))}")

    stream_subreddits(debug_handler)
