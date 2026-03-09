"""
Telegram bot config from environment.
"""
import os
import re

# Load from env; caller may load .env via start_telegram.sh or python-dotenv
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_ALLOWED_USERS_RAW = os.environ.get("TELEGRAM_ALLOWED_USERS", "").strip()
BRIDGE_URL = os.environ.get("BRIDGE_URL", "http://localhost:8765").rstrip("/")
API_URL = os.environ.get("API_URL", "http://localhost:8000").rstrip("/")


def get_allowed_user_ids():
    """Parse TELEGRAM_ALLOWED_USERS (comma-separated) into a set of ints (or str if not numeric)."""
    if not TELEGRAM_ALLOWED_USERS_RAW:
        return set()
    out = set()
    for part in re.split(r"[\s,]+", TELEGRAM_ALLOWED_USERS_RAW):
        part = part.strip()
        if not part:
            continue
        try:
            out.add(int(part))
        except ValueError:
            out.add(part)
    return out


ALLOWED_USER_IDS = get_allowed_user_ids()
