"""Daily lesson JobQueue callback."""

from __future__ import annotations

import logging
import random

from telegram.ext import ContextTypes

from bot import db
from bot import keyboards as kb
from bot.content_loader import Curriculum
from bot.premium import can_access_module

log = logging.getLogger(__name__)


async def daily_lesson_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    curriculum: Curriculum = context.application.bot_data["curriculum"]
    user_ids = db.users_with_daily_opt_in()
    if not user_ids:
        log.info("daily_job: no opted-in users")
        return

    # Prefer free modules first for free users; premium users get full track.
    log.info("daily_job: messaging %d users", len(user_ids))
    for uid in user_ids:
        try:
            await _send_daily(context, curriculum, uid)
        except Exception:
            log.exception("daily_job failed for user_id=%s", uid)


async def _send_daily(
    context: ContextTypes.DEFAULT_TYPE, curriculum: Curriculum, user_id: int
) -> None:
    accessible = [
        m for m in curriculum.modules if can_access_module(user_id, m.id)
    ]
    modules_meta = [(m.id, len(m.lessons)) for m in accessible]
    nxt = db.next_unread_lesson(user_id, modules_meta)
    if nxt is None:
        fact = random.choice(curriculum.facts)
        text = (
            "📅 <b>Daily AvGeek</b>\n\n"
            "You’re caught up on lessons you can access — here’s a fact instead:\n\n"
            f"✈️ {fact}"
        )
        await context.bot.send_message(
            chat_id=user_id,
            text=text,
            parse_mode="HTML",
            reply_markup=kb.after_fact(),
        )
        db.touch_streak(user_id)
        return

    mod_id, idx = nxt
    mod = curriculum.by_id(mod_id)
    if not mod:
        return
    lesson = mod.lessons[idx]
    db.mark_lesson(user_id, mod_id, idx)
    db.touch_streak(user_id)
    # Import here to avoid circular import at module load.
    from bot.handlers import rich

    text = (
        f"📅 <b>Daily lesson</b>\n"
        f"{mod.emoji} <b>{mod.title}</b> · Lesson {idx + 1}/{len(mod.lessons)}\n\n"
        f"<b>{lesson.title}</b>\n\n"
        f"{rich(lesson.body)}"
    )
    await context.bot.send_message(
        chat_id=user_id,
        text=text,
        parse_mode="HTML",
        reply_markup=kb.lesson_nav(mod, idx),
    )
