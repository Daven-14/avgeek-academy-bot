"""SQLite persistence keyed by Telegram user id."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator

from bot.config import DATA_DIR, DB_PATH, PREMIUM_DAYS

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id     INTEGER PRIMARY KEY,
    username    TEXT,
    first_name  TEXT,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lesson_progress (
    user_id       INTEGER NOT NULL,
    module_id     TEXT    NOT NULL,
    lesson_index  INTEGER NOT NULL,
    completed_at  TEXT    NOT NULL,
    PRIMARY KEY (user_id, module_id, lesson_index)
);

CREATE TABLE IF NOT EXISTS quiz_attempts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL,
    module_id     TEXT    NOT NULL,
    score         INTEGER NOT NULL,
    total         INTEGER NOT NULL,
    completed_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS quiz_best (
    user_id     INTEGER NOT NULL,
    module_id   TEXT    NOT NULL,
    best_score  INTEGER NOT NULL,
    total       INTEGER NOT NULL,
    PRIMARY KEY (user_id, module_id)
);

CREATE TABLE IF NOT EXISTS certificates (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    module_id   TEXT    NOT NULL,
    title       TEXT    NOT NULL,
    awarded_at  TEXT    NOT NULL,
    UNIQUE (user_id, module_id)
);
"""

# Columns added after the initial schema (SQLite-friendly migrations).
_USER_COLUMNS: tuple[tuple[str, str], ...] = (
    ("goal", "TEXT"),
    ("streak_count", "INTEGER NOT NULL DEFAULT 0"),
    ("last_active_date", "TEXT"),
    ("daily_opt_in", "INTEGER NOT NULL DEFAULT 0"),
    ("is_premium", "INTEGER NOT NULL DEFAULT 0"),
    ("premium_until", "TEXT"),
    ("onboarded", "INTEGER NOT NULL DEFAULT 0"),
)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def utc_today_str() -> str:
    return datetime.now(timezone.utc).date().isoformat()


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(r["name"]) for r in rows}


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        existing = _column_names(conn, "users")
        added_onboarded = False
        for col, decl in _USER_COLUMNS:
            if col not in existing:
                conn.execute(f"ALTER TABLE users ADD COLUMN {col} {decl}")
                if col == "onboarded":
                    added_onboarded = True
        # Pre-existing accounts skip the new onboarding flow once.
        if added_onboarded:
            conn.execute("UPDATE users SET onboarded = 1 WHERE onboarded = 0")


def upsert_user(user_id: int, username: str | None, first_name: str | None) -> None:
    with connect() as conn:
        existing = conn.execute(
            "SELECT user_id FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE users SET username = ?, first_name = ? WHERE user_id = ?",
                (username, first_name, user_id),
            )
        else:
            conn.execute(
                "INSERT INTO users (user_id, username, first_name, created_at) "
                "VALUES (?, ?, ?, ?)",
                (user_id, username, first_name, _utcnow()),
            )


def get_user(user_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
    if row is None:
        return None
    return dict(row)


def is_onboarded(user_id: int) -> bool:
    user = get_user(user_id)
    return bool(user and user.get("onboarded"))


def set_goal_and_onboard(user_id: int, goal: str) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE users SET goal = ?, onboarded = 1 WHERE user_id = ?",
            (goal, user_id),
        )


def touch_streak(user_id: int) -> int:
    """Update streak on a meaningful action. Returns current streak_count."""
    today = utc_today_str()
    with connect() as conn:
        row = conn.execute(
            "SELECT streak_count, last_active_date FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            return 0
        last = row["last_active_date"]
        streak = int(row["streak_count"] or 0)
        if last == today:
            return streak
        yesterday = (
            datetime.now(timezone.utc).date() - timedelta(days=1)
        ).isoformat()
        if last == yesterday:
            streak = streak + 1
        else:
            streak = 1
        conn.execute(
            "UPDATE users SET streak_count = ?, last_active_date = ? WHERE user_id = ?",
            (streak, today, user_id),
        )
        return streak


def get_streak(user_id: int) -> int:
    user = get_user(user_id)
    if not user:
        return 0
    return int(user.get("streak_count") or 0)


def set_daily_opt_in(user_id: int, enabled: bool) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE users SET daily_opt_in = ? WHERE user_id = ?",
            (1 if enabled else 0, user_id),
        )


def get_daily_opt_in(user_id: int) -> bool:
    user = get_user(user_id)
    return bool(user and user.get("daily_opt_in"))


def users_with_daily_opt_in() -> list[int]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT user_id FROM users WHERE daily_opt_in = 1"
        ).fetchall()
    return [int(r["user_id"]) for r in rows]


def set_premium(user_id: int, *, days: int = PREMIUM_DAYS) -> str:
    """Grant premium for `days` from now (or extend from existing until). Returns ISO until."""
    now = datetime.now(timezone.utc)
    with connect() as conn:
        row = conn.execute(
            "SELECT is_premium, premium_until FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        base = now
        if row and row["premium_until"]:
            try:
                existing = datetime.fromisoformat(str(row["premium_until"]))
                if existing.tzinfo is None:
                    existing = existing.replace(tzinfo=timezone.utc)
                if existing > now:
                    base = existing
            except ValueError:
                pass
        until = base + timedelta(days=days)
        until_s = until.isoformat(timespec="seconds")
        conn.execute(
            "UPDATE users SET is_premium = 1, premium_until = ? WHERE user_id = ?",
            (until_s, user_id),
        )
        return until_s


def clear_expired_premium(user_id: int) -> None:
    user = get_user(user_id)
    if not user or not user.get("is_premium"):
        return
    until = user.get("premium_until")
    if not until:
        return
    try:
        exp = datetime.fromisoformat(str(until))
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
    except ValueError:
        return
    if exp <= datetime.now(timezone.utc):
        with connect() as conn:
            conn.execute(
                "UPDATE users SET is_premium = 0 WHERE user_id = ?",
                (user_id,),
            )


def raw_premium_flags(user_id: int) -> tuple[bool, str | None]:
    """Return (is_premium flag, premium_until) after clearing expiry in DB."""
    clear_expired_premium(user_id)
    user = get_user(user_id)
    if not user:
        return False, None
    return bool(user.get("is_premium")), user.get("premium_until")


def mark_lesson(user_id: int, module_id: str, lesson_index: int) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO lesson_progress "
            "(user_id, module_id, lesson_index, completed_at) VALUES (?, ?, ?, ?)",
            (user_id, module_id, lesson_index, _utcnow()),
        )


def lessons_done(user_id: int, module_id: str) -> set[int]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT lesson_index FROM lesson_progress "
            "WHERE user_id = ? AND module_id = ?",
            (user_id, module_id),
        ).fetchall()
    return {int(r["lesson_index"]) for r in rows}


def next_unread_lesson(
    user_id: int, modules: list[tuple[str, int]]
) -> tuple[str, int] | None:
    """modules: list of (module_id, lesson_count). Returns first unread (mod, idx)."""
    for mod_id, count in modules:
        done = lessons_done(user_id, mod_id)
        for idx in range(count):
            if idx not in done:
                return mod_id, idx
    return None


def record_quiz(user_id: int, module_id: str, score: int, total: int) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO quiz_attempts "
            "(user_id, module_id, score, total, completed_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, module_id, score, total, _utcnow()),
        )
        best = conn.execute(
            "SELECT best_score FROM quiz_best WHERE user_id = ? AND module_id = ?",
            (user_id, module_id),
        ).fetchone()
        if best is None:
            conn.execute(
                "INSERT INTO quiz_best (user_id, module_id, best_score, total) "
                "VALUES (?, ?, ?, ?)",
                (user_id, module_id, score, total),
            )
        elif score > int(best["best_score"]):
            conn.execute(
                "UPDATE quiz_best SET best_score = ?, total = ? "
                "WHERE user_id = ? AND module_id = ?",
                (score, total, user_id, module_id),
            )


def quiz_best(user_id: int, module_id: str) -> tuple[int, int] | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT best_score, total FROM quiz_best "
            "WHERE user_id = ? AND module_id = ?",
            (user_id, module_id),
        ).fetchone()
    if row is None:
        return None
    return int(row["best_score"]), int(row["total"])


def progress_snapshot(user_id: int) -> dict[str, Any]:
    """Per-module lesson counts and best quiz scores, plus lifetime accuracy."""
    with connect() as conn:
        lesson_rows = conn.execute(
            "SELECT module_id, COUNT(*) AS n FROM lesson_progress "
            "WHERE user_id = ? GROUP BY module_id",
            (user_id,),
        ).fetchall()
        best_rows = conn.execute(
            "SELECT module_id, best_score, total FROM quiz_best WHERE user_id = ?",
            (user_id,),
        ).fetchall()
        lifetime = conn.execute(
            "SELECT COALESCE(SUM(score), 0) AS correct, "
            "       COALESCE(SUM(total), 0) AS asked, "
            "       COUNT(*) AS attempts "
            "FROM quiz_attempts WHERE user_id = ?",
            (user_id,),
        ).fetchone()

    return {
        "lessons": {r["module_id"]: int(r["n"]) for r in lesson_rows},
        "best": {
            r["module_id"]: (int(r["best_score"]), int(r["total"])) for r in best_rows
        },
        "quiz_correct": int(lifetime["correct"]),
        "quiz_asked": int(lifetime["asked"]),
        "quiz_attempts": int(lifetime["attempts"]),
    }


def try_award_certificate(
    user_id: int, module_id: str, title: str, lesson_count: int
) -> bool:
    """Award a cert if all lessons done and best quiz >= 80%. Returns True if newly awarded."""
    done = lessons_done(user_id, module_id)
    if len(done) < lesson_count:
        return False
    best = quiz_best(user_id, module_id)
    if not best or best[1] <= 0:
        return False
    pct = 100.0 * best[0] / best[1]
    if pct < 80.0:
        return False
    with connect() as conn:
        existing = conn.execute(
            "SELECT id FROM certificates WHERE user_id = ? AND module_id = ?",
            (user_id, module_id),
        ).fetchone()
        if existing:
            return False
        conn.execute(
            "INSERT INTO certificates (user_id, module_id, title, awarded_at) "
            "VALUES (?, ?, ?, ?)",
            (user_id, module_id, title, _utcnow()),
        )
        return True


def list_certificates(user_id: int) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT module_id, title, awarded_at FROM certificates "
            "WHERE user_id = ? ORDER BY awarded_at ASC",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]

