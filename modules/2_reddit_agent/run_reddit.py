"""
run_reddit.py
Background worker — starts the Reddit monitor and feeds events to the reply engine.
Handles graceful restarts and rate-limit backoff.
"""

import logging
import signal
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from monitor      import stream_subreddits
from reply_engine import handle_event

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

_running = True


def _shutdown(signum, frame):
    global _running
    log.info("Shutdown signal received.")
    _running = False
    sys.exit(0)


signal.signal(signal.SIGINT,  _shutdown)
signal.signal(signal.SIGTERM, _shutdown)


def main():
    log.info("Reddit agent starting...")
    retry = 0
    while _running:
        try:
            stream_subreddits(on_match=handle_event)
            retry = 0
        except KeyboardInterrupt:
            break
        except Exception as e:
            wait = min(300, 10 * (2 ** retry))
            log.error(f"Stream crashed: {e}. Restarting in {wait}s...")
            time.sleep(wait)
            retry += 1


if __name__ == "__main__":
    main()
