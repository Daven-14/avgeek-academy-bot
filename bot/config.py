"""Paths, environment, and startup checks."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
CONTENT_DIR = ROOT_DIR / "content"
DIAGRAMS_DIR = CONTENT_DIR / "diagrams"
DATA_DIR = ROOT_DIR / "data"
DB_PATH = DATA_DIR / "progress.db"

load_dotenv(ROOT_DIR / ".env")

# Free modules for non-premium users.
FREE_MODULE_IDS: frozenset[str] = frozenset({"aero", "struct"})

PREMIUM_PAYLOAD = "premium_30d"
PREMIUM_DAYS = 30
PREMIUM_TITLE = "AvGeek Pro — 30 days"
PREMIUM_DESCRIPTION = (
    "Unlock all curriculum modules, certificates, and Pro features for 30 days."
)


def telegram_token() -> str:
    """Return the bot token or exit with a clear error."""
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token or token in {"YOUR_TOKEN_HERE", "changeme", "replace-me"}:
        sys.stderr.write(
            "\n"
            "ERROR: TELEGRAM_BOT_TOKEN is not set.\n"
            "\n"
            "1. Message @BotFather on Telegram and create a bot.\n"
            "2. Copy the token into a .env file in the project root:\n"
            "     TELEGRAM_BOT_TOKEN=123456:ABC-your-token\n"
            "   (see .env.example)\n"
            "3. Run again:  python -m bot\n"
            "\n"
        )
        sys.exit(1)
    return token


def premium_stars_price() -> int:
    raw = (os.getenv("PREMIUM_STARS_PRICE") or "150").strip()
    try:
        price = int(raw)
    except ValueError:
        price = 150
    return max(1, price)


def premium_bypass_user_ids() -> frozenset[int]:
    raw = (os.getenv("PREMIUM_BYPASS_USER_IDS") or "").strip()
    if not raw:
        return frozenset()
    ids: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.add(int(part))
        except ValueError:
            continue
    return frozenset(ids)


def webhook_url() -> str | None:
    url = (os.getenv("WEBHOOK_URL") or "").strip().rstrip("/")
    return url or None


def listen_port() -> int:
    raw = (os.getenv("PORT") or "8080").strip()
    try:
        return int(raw)
    except ValueError:
        return 8080


def webhook_path() -> str:
    path = (os.getenv("WEBHOOK_PATH") or "/telegram").strip()
    if not path.startswith("/"):
        path = "/" + path
    return path


def daily_lesson_hour() -> int:
    raw = (os.getenv("DAILY_LESSON_HOUR") or "9").strip()
    try:
        hour = int(raw)
    except ValueError:
        hour = 9
    return max(0, min(23, hour))
