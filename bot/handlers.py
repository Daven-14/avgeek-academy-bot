"""Command and callback handlers for AvGeek Academy."""

from __future__ import annotations

import html
import logging
import random
from typing import Any

from telegram import InputFile, Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from bot import certificates as certs
from bot import db, keyboards as kb
from bot import premium as prem
from bot.config import premium_stars_price
from bot.content_loader import Curriculum, Module, diagram_path

log = logging.getLogger(__name__)

DISCLAIMER_ONE_LINER = (
    "<i>Teaching aid only — not flight instruction. See /legal.</i>"
)

ONBOARD_ASK = (
    "<b>Welcome to AvGeek Academy</b> ✈️\n\n"
    "Before we take off — what brings you here?"
)

GOAL_LABELS = {
    "curious": "Curious flyer",
    "student": "Student pilot",
    "engineer": "Engineer / avgeek",
    "browse": "Just browsing",
}

STREAK_MILESTONES = (3, 7, 14)


def _welcome_body(user_id: int, first_name: str | None = None) -> str:
    name = html.escape((first_name or "").strip())
    hello = f"Hi {name}! " if name else ""
    streak = db.get_streak(user_id)
    streak_bit = (
        f"🔥 <b>{streak}</b>-day streak · " if streak else ""
    )
    return (
        f"{hello}<b>AvGeek Academy</b> — entirely free.\n"
        f"{streak_bit}{prem.premium_status_line(user_id)}\n\n"
        "Continue where you left off, follow the path, or drill missed quizzes.\n\n"
        f"{DISCLAIMER_ONE_LINER}"
    )


HELP = (
    "<b>Commands</b>\n"
    "/start — welcome and main menu\n"
    "/menu — jump back to the main menu\n"
    "/path — learning roadmap with checkmarks\n"
    "/review — spaced review (missed + practice)\n"
    "/help — this message\n"
    "/progress — bars, streak, reviews due\n"
    "/fact — a random aviation fact\n"
    "/term &lt;word&gt; — look up a glossary term\n"
    "/daily on|off — daily lesson push (~09:00 UTC)\n"
    "/certificate — view earned certificates\n"
    "/pro — about this free bot (+ optional tip)\n"
    "/buy — optional tip via Telegram Stars\n"
    "/legal — disclaimer, terms, privacy\n\n"
    "<b>How to learn</b>\n"
    "Follow /path, use <b>Continue learning</b> for the next unread lesson, "
    "then quiz. Score ≥80% with all lessons done to earn a certificate.\n\n"
    "<b>Free forever</b>\n"
    "All 7 modules are unlocked for everyone. Stars tips are optional support.\n\n"
    "This bot is for curious beginners through intermediate learners. "
    "It is not a substitute for a ground school or a type rating."
)

LEGAL = (
    "<b>Disclaimer</b>\n"
    "AvGeek Academy is a <b>teaching aid</b> for aviation technology enthusiasts. "
    "It is <b>not</b> flight instruction, ground school, type-rating material, or "
    "operational guidance. Always defer to your instructor, AFM, CAA, and current charts. "
    "No liability for decisions made using this content.\n\n"
    "<b>Terms</b>\n"
    "Use the bot for personal learning. Do not rely on it for flight planning or "
    "airworthiness decisions. We may change curriculum. Optional Telegram Stars "
    "tips follow Telegram’s payment rules; they are never required for content.\n\n"
    "<b>Privacy</b>\n"
    "We store: Telegram user id, optional username/first name, learning progress, "
    "optional goal, streak dates, daily opt-in, optional tip status, wrong-answer "
    "review bank, milestones, and certificates. "
    "We do <b>not</b> sell your data. Progress lives in our SQLite database on the "
    "server that runs the bot.\n\n"
    "Questions? Message the bot operator from the landing page contact."
)

GLOSSARY_PROMPT = (
    "Send a word or short phrase to look up — for example "
    "<code>lift</code>, <code>turbofan</code>, or <code>ILS</code>.\n\n"
    "You can also type <code>/term stall</code> any time."
)


def rich(text: str) -> str:
    """Escape HTML, then restore the few tags used in lesson YAML."""
    escaped = html.escape(text or "", quote=False)
    for raw, tag in (
        ("&lt;b&gt;", "<b>"),
        ("&lt;/b&gt;", "</b>"),
        ("&lt;i&gt;", "<i>"),
        ("&lt;/i&gt;", "</i>"),
        ("&lt;code&gt;", "<code>"),
        ("&lt;/code&gt;", "</code>"),
    ):
        escaped = escaped.replace(raw, tag)
    return escaped


def _cur(context: ContextTypes.DEFAULT_TYPE) -> Curriculum:
    return context.application.bot_data["curriculum"]


def _uid(update: Update) -> int:
    user = update.effective_user
    if user is None:
        raise RuntimeError("Update has no user")
    return user.id


def _touch_user(update: Update) -> None:
    user = update.effective_user
    if user is None:
        return
    db.upsert_user(user.id, user.username, user.first_name)


def _meaningful(user_id: int) -> int:
    return db.touch_streak(user_id)


def _menu_markup(user_id: int) -> Any:
    return kb.main_menu(
        daily_on=db.get_daily_opt_in(user_id),
        streak=db.get_streak(user_id),
    )


def _progress_bar(done: int, total: int, width: int = 6) -> str:
    if total <= 0:
        return "░" * width
    filled = int(round(width * min(done, total) / total))
    filled = max(0, min(width, filled))
    return "█" * filled + "░" * (width - filled)


def _module_list_for_continue(curriculum: Curriculum) -> list[tuple[str, int]]:
    return [(m.id, len(m.lessons)) for m in curriculum.modules]


def _completed_module_ids(user_id: int, curriculum: Curriculum) -> set[str]:
    return {
        m.id
        for m in curriculum.modules
        if db.module_is_complete(user_id, m.id, len(m.lessons))
    }


def _next_incomplete_module(
    user_id: int, curriculum: Curriculum
) -> Module | None:
    completed = _completed_module_ids(user_id, curriculum)
    for m in curriculum.modules:
        if m.id not in completed:
            return m
    return None


def _path_percent(user_id: int, curriculum: Curriculum) -> int:
    snap = db.progress_snapshot(user_id)
    total = sum(len(m.lessons) for m in curriculum.modules)
    done = sum(snap["lessons"].get(m.id, 0) for m in curriculum.modules)
    if total <= 0:
        return 0
    return int(100 * done / total)


async def _edit_or_reply(
    update: Update,
    text: str,
    reply_markup: Any,
) -> None:
    query = update.callback_query
    if query and query.message:
        try:
            await query.edit_message_text(
                text, parse_mode="HTML", reply_markup=reply_markup
            )
            return
        except BadRequest as exc:
            if "not modified" in str(exc).lower():
                return
            log.debug("edit_message_text failed: %s", exc)
    if update.effective_message:
        await update.effective_message.reply_text(
            text, parse_mode="HTML", reply_markup=reply_markup
        )


def _module_overview(mod: Module, user_id: int) -> str:
    seen = db.lessons_done(user_id, mod.id)
    snap = db.progress_snapshot(user_id)
    best = snap["best"].get(mod.id)
    best_line = (
        f"Best quiz: <b>{best[0]}/{best[1]}</b>"
        if best
        else "Quiz: not attempted yet"
    )
    bar = _progress_bar(len(seen), len(mod.lessons))
    return (
        f"{mod.emoji} <b>{html.escape(mod.title)}</b>\n\n"
        f"{rich(mod.blurb)}\n\n"
        f"Lessons: <code>{bar}</code> <b>{len(seen)}/{len(mod.lessons)}</b> · "
        f"{len(mod.quizzes)} quiz questions\n"
        f"{best_line}"
    )


def _render_lesson(mod: Module, idx: int, *, simple: bool = False) -> str:
    lesson = mod.lessons[idx]
    body = lesson.simple if simple else lesson.body
    tag = " · simpler take" if simple else ""
    return (
        f"{mod.emoji} <b>{html.escape(mod.title)}</b>\n"
        f"<i>Lesson {idx + 1} of {len(mod.lessons)}{tag}</i>\n\n"
        f"<b>{html.escape(lesson.title)}</b>\n\n"
        f"{rich(body)}"
    )


def _render_progress(user_id: int, curriculum: Curriculum) -> str:
    snap = db.progress_snapshot(user_id)
    streak = db.get_streak(user_id)
    reviews = db.wrong_answer_count(user_id)
    overall = _path_percent(user_id, curriculum)
    lines = [
        "<b>Your progress</b>\n",
        f"🔥 Streak: <b>{streak}</b> day{'s' if streak != 1 else ''} · "
        f"🧠 Reviews due: <b>{reviews}</b> · "
        f"Overall <b>{overall}%</b>\n",
        f"{prem.premium_status_line(user_id)}\n",
    ]
    total_lessons = 0
    done_lessons = 0
    for mod in curriculum.modules:
        total_lessons += len(mod.lessons)
        n = snap["lessons"].get(mod.id, 0)
        done_lessons += n
        best = snap["best"].get(mod.id)
        quiz_bit = f" · quiz {best[0]}/{best[1]}" if best else " · quiz —"
        bar = _progress_bar(n, len(mod.lessons))
        done_mark = " ☑️" if db.module_is_complete(user_id, mod.id, len(mod.lessons)) else ""
        lines.append(
            f"{mod.emoji} <b>{html.escape(mod.title)}</b>{done_mark}\n"
            f"    <code>{bar}</code> {n}/{len(mod.lessons)}{quiz_bit}"
        )
    asked = snap["quiz_asked"]
    correct = snap["quiz_correct"]
    pct = f"{(100 * correct / asked):.0f}%" if asked else "—"
    lines.append("")
    lines.append(
        f"Overall: <b>{done_lessons}/{total_lessons}</b> lessons · "
        f"{snap['quiz_attempts']} quiz attempt(s) · accuracy {pct}"
        + (f" ({correct}/{asked})" if asked else "")
    )
    if done_lessons == 0 and asked == 0:
        lines.append("\nNothing saved yet — open /path and start a lesson.")
    return "\n".join(lines)


def _render_path(user_id: int, curriculum: Curriculum) -> str:
    snap = db.progress_snapshot(user_id)
    completed = _completed_module_ids(user_id, curriculum)
    next_mod = _next_incomplete_module(user_id, curriculum)
    overall = _path_percent(user_id, curriculum)
    lines = [
        "<b>Learning path</b>\n",
        f"Overall <b>{overall}%</b> · "
        f"{len(completed)}/{len(curriculum.modules)} modules complete\n",
    ]
    for mod in curriculum.modules:
        n = snap["lessons"].get(mod.id, 0)
        total = len(mod.lessons)
        bar = _progress_bar(n, total)
        if mod.id in completed:
            mark = "☑️"
            here = ""
        else:
            mark = "☐"
            here = "  <b>← You are here</b>" if next_mod and mod.id == next_mod.id else ""
        lines.append(
            f"{mark} {mod.emoji} <b>{html.escape(mod.title)}</b>{here}\n"
            f"    <code>{bar}</code> {n}/{total}"
        )
    lines.append("\nTap a module to open it, or Continue for the next unread lesson.")
    return "\n".join(lines)


def _render_fact(curriculum: Curriculum) -> str:
    fact = random.choice(curriculum.facts)
    return f"✈️ <b>Aviation fact</b>\n\n{rich(fact)}"


def _quiz_state(context: ContextTypes.DEFAULT_TYPE) -> dict[str, Any]:
    return context.user_data.setdefault("quiz", {})


def _start_quiz_state(context: ContextTypes.DEFAULT_TYPE, mod_id: str) -> dict[str, Any]:
    state = {
        "mod": mod_id,
        "idx": 0,
        "score": 0,
        "answered": [],
        "finished": False,
    }
    context.user_data["quiz"] = state
    return state


def _quiz_question_text(mod: Module, q_idx: int) -> str:
    item = mod.quizzes[q_idx]
    return (
        f"{mod.emoji} <b>{html.escape(mod.title)} quiz</b>\n"
        f"<i>Question {q_idx + 1} of {len(mod.quizzes)}</i>\n\n"
        f"{html.escape(item.question)}"
    )


def _pro_text(user_id: int) -> str:
    price = premium_stars_price()
    status = prem.premium_status_line(user_id)
    return (
        f"<b>Thanks for learning</b>\n\n"
        f"This bot is <b>entirely free</b> — all 7 modules, quizzes, "
        f"certificates, path, and review. No paywall.\n\n"
        f"{status}\n\n"
        f"Optional tip via Telegram Stars ({price} ⭐) supports hosting &amp; new lessons. "
        f"Never required for content.\n\n"
        "Tap <b>Send optional tip</b> or /buy if you’d like to chip in."
    )


async def _maybe_celebrate_streak(
    update: Update, user_id: int, streak: int
) -> None:
    if streak not in STREAK_MILESTONES:
        return
    key = f"streak:{streak}"
    if not db.mark_milestone_sent(user_id, key):
        return
    if not update.effective_message:
        return
    flames = "🔥" * min(streak, 7)
    text = (
        f"{flames} <b>{streak}-day streak!</b>\n\n"
        f"Consistency beats cramming. Keep the chain going — "
        f"a short lesson or /review counts."
    )
    await update.effective_message.reply_text(
        text, parse_mode="HTML", reply_markup=kb.back_menu()
    )


async def _maybe_award_cert(
    update: Update, user_id: int, mod: Module
) -> None:
    awarded = db.try_award_certificate(
        user_id, mod.id, mod.title, len(mod.lessons)
    )
    # Module-complete celebration (once), even if cert was already in DB from race
    complete = db.module_is_complete(user_id, mod.id, len(mod.lessons))
    if complete and update.effective_message:
        key = f"mod:{mod.id}"
        if db.mark_milestone_sent(user_id, key):
            text = (
                f"🎉 <b>Module complete!</b>\n\n"
                f"You finished <b>{html.escape(mod.title)}</b> — all lessons "
                f"and quiz ≥80%. That is real progress.\n\n"
                f"Grab your certificate and keep flying the path."
            )
            await update.effective_message.reply_text(
                text, parse_mode="HTML", reply_markup=kb.module_complete_cta(mod.id)
            )

    if not awarded or not update.effective_message:
        return
    name = update.effective_user.first_name if update.effective_user else None
    cert_list = db.list_certificates(user_id)
    awarded_at = ""
    for c in cert_list:
        if c["module_id"] == mod.id:
            awarded_at = str(c["awarded_at"])
            break
    png = certs.render_certificate_png(name, mod.title, awarded_at)
    if png:
        await update.effective_message.reply_photo(
            photo=InputFile(png, filename=f"cert_{mod.id}.png"),
            caption=f"🏅 {mod.title} — AvGeek Academy",
        )


async def _show_module_home(
    update: Update, context: ContextTypes.DEFAULT_TYPE, mod: Module, user_id: int
) -> None:
    seen = db.lessons_done(user_id, mod.id)
    overview = _module_overview(mod, user_id)
    diagram = diagram_path(mod.id)
    markup = kb.module_home(mod, len(seen))

    if diagram is not None and update.effective_message:
        query = update.callback_query
        if query and query.message:
            try:
                await query.edit_message_text(
                    overview, parse_mode="HTML", reply_markup=markup
                )
            except BadRequest:
                await update.effective_message.reply_text(
                    overview, parse_mode="HTML", reply_markup=markup
                )
        else:
            await update.effective_message.reply_text(
                overview, parse_mode="HTML", reply_markup=markup
            )
        try:
            with diagram.open("rb") as fh:
                await update.effective_message.reply_photo(
                    photo=InputFile(fh, filename=diagram.name),
                    caption=f"{mod.emoji} {mod.title}",
                )
        except OSError as exc:
            log.warning("Failed to send diagram %s: %s", diagram, exc)
        return

    await _edit_or_reply(update, overview, markup)


async def _smart_continue(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int
) -> None:
    curriculum = _cur(context)
    nxt = db.next_unread_lesson(user_id, _module_list_for_continue(curriculum))
    if nxt is None:
        text = (
            "🏁 <b>All lessons read!</b>\n\n"
            "Try a quiz on any module, run /review, or revisit favourites from /path."
        )
        await _edit_or_reply(update, text, kb.path_menu(
            curriculum.modules,
            completed_ids=_completed_module_ids(user_id, curriculum),
            next_mod_id=None,
        ))
        return
    mod_id, idx = nxt
    await _show_lesson(update, context, mod_id, idx, simple=False)


def _build_review_queue(
    user_id: int, curriculum: Curriculum, limit: int = 3
) -> list[tuple[str, int]]:
    wrong = db.list_wrong_answers(user_id)
    queue: list[tuple[str, int]] = []
    seen: set[tuple[str, int]] = set()
    for mod_id, q_idx in wrong:
        mod = curriculum.by_id(mod_id)
        if not mod or not (0 <= q_idx < len(mod.quizzes)):
            continue
        key = (mod_id, q_idx)
        if key in seen:
            continue
        seen.add(key)
        queue.append(key)
        if len(queue) >= limit:
            return queue

    # Gentle practice from finished (or started) modules
    pool: list[tuple[str, int]] = []
    for mod in curriculum.modules:
        done = db.lessons_done(user_id, mod.id)
        if not done and not db.quiz_best(user_id, mod.id):
            continue
        for i in range(len(mod.quizzes)):
            key = (mod.id, i)
            if key not in seen:
                pool.append(key)
    random.shuffle(pool)
    for key in pool:
        queue.append(key)
        if len(queue) >= limit:
            break
    return queue


async def _begin_review(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int
) -> None:
    curriculum = _cur(context)
    queue = _build_review_queue(user_id, curriculum, limit=3)
    if not queue:
        text = (
            "🧠 <b>Review</b>\n\n"
            "No drills yet — finish a lesson or take a quiz first, "
            "then come back to sharpen what stuck."
        )
        await _edit_or_reply(update, text, _menu_markup(user_id))
        return
    from_wrong = db.wrong_answer_count(user_id) > 0
    context.user_data["review"] = {
        "queue": queue,
        "idx": 0,
        "score": 0,
        "from_wrong": from_wrong,
    }
    intro = (
        "🧠 <b>Spaced review</b> — 3 quick questions\n"
        + (
            "Pulled from misses + practice.\n\n"
            if from_wrong
            else "Gentle practice from modules you’ve touched.\n\n"
        )
    )
    await _show_review_question(update, context, prepend=intro)


async def _show_review_question(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    prepend: str = "",
) -> None:
    state = context.user_data.get("review") or {}
    queue: list[tuple[str, int]] = list(state.get("queue") or [])
    idx = int(state.get("idx") or 0)
    if idx >= len(queue):
        await _finish_review(update, context)
        return
    mod_id, q_idx = queue[idx]
    mod = _cur(context).by_id(mod_id)
    if not mod or not (0 <= q_idx < len(mod.quizzes)):
        state["idx"] = idx + 1
        await _show_review_question(update, context, prepend=prepend)
        return
    item = mod.quizzes[q_idx]
    text = (
        f"{prepend}"
        f"{mod.emoji} <b>{html.escape(mod.title)}</b>\n"
        f"<i>Review {idx + 1} of {len(queue)}</i>\n\n"
        f"{html.escape(item.question)}"
    )
    await _edit_or_reply(update, text, kb.review_choices(mod_id, q_idx, item))


async def _grade_review(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    mod_id: str,
    q_idx: int,
    choice: int,
) -> None:
    state = context.user_data.get("review") or {}
    queue: list[tuple[str, int]] = list(state.get("queue") or [])
    idx = int(state.get("idx") or 0)
    mod = _cur(context).by_id(mod_id)
    if not mod or not (0 <= q_idx < len(mod.quizzes)):
        await _edit_or_reply(update, "That review item expired.", _menu_markup(_uid(update)))
        return
    item = mod.quizzes[q_idx]
    correct = choice == item.answer
    uid = _uid(update)
    if correct:
        state["score"] = int(state.get("score") or 0) + 1
        db.clear_wrong_answer(uid, mod_id, q_idx)
        verdict = "✅ <b>Correct</b>"
    else:
        db.record_wrong_answer(uid, mod_id, q_idx)
        letters = "ABCD"
        right = letters[item.answer] if item.answer < len(letters) else str(item.answer)
        verdict = f"❌ <b>Not quite</b> — answer <b>{right}</b>"
    last = idx >= len(queue) - 1
    score = int(state.get("score") or 0)
    text = (
        f"{mod.emoji} <b>{html.escape(mod.title)}</b>\n"
        f"<i>Review {idx + 1} of {len(queue)}</i>\n\n"
        f"{html.escape(item.question)}\n\n"
        f"{verdict}\n\n"
        f"{rich(item.explanation)}"
    )
    if last:
        text += (
            f"\n\n🧠 <b>Review complete</b> — score <b>{score}/{len(queue)}</b>"
        )
        context.user_data.pop("review", None)
    else:
        context.user_data["review"] = state
    await _edit_or_reply(update, text, kb.review_next(done=last))


async def _finish_review(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    state = context.user_data.get("review") or {}
    queue = list(state.get("queue") or [])
    score = int(state.get("score") or 0)
    total = len(queue) or 1
    text = (
        f"🧠 <b>Review complete</b>\n\n"
        f"Score: <b>{score}/{len(queue)}</b>\n\n"
        + (
            "Sharp. Come back after the next quiz for fresh misses."
            if score == len(queue)
            else "Nice drill. Misses stay in your review bank until you clear them."
        )
    )
    await _edit_or_reply(update, text, kb.review_next(done=True))
    context.user_data.pop("review", None)
    _ = total


# --- commands ----------------------------------------------------------------


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _touch_user(update)
    user = update.effective_user
    assert user is not None
    if not db.is_onboarded(user.id):
        await update.effective_message.reply_text(
            ONBOARD_ASK, parse_mode="HTML", reply_markup=kb.onboarding_goals()
        )
        return
    await update.effective_message.reply_text(
        _welcome_body(user.id, user.first_name),
        parse_mode="HTML",
        reply_markup=_menu_markup(user.id),
    )


async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _touch_user(update)
    user = update.effective_user
    assert user is not None
    await update.effective_message.reply_text(
        _welcome_body(user.id, user.first_name),
        parse_mode="HTML",
        reply_markup=_menu_markup(user.id),
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _touch_user(update)
    await update.effective_message.reply_text(
        HELP, parse_mode="HTML", reply_markup=kb.back_menu()
    )


async def cmd_progress(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _touch_user(update)
    text = _render_progress(_uid(update), _cur(context))
    await update.effective_message.reply_text(
        text, parse_mode="HTML", reply_markup=kb.back_menu()
    )


async def cmd_path(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _touch_user(update)
    uid = _uid(update)
    curriculum = _cur(context)
    next_mod = _next_incomplete_module(uid, curriculum)
    await update.effective_message.reply_text(
        _render_path(uid, curriculum),
        parse_mode="HTML",
        reply_markup=kb.path_menu(
            curriculum.modules,
            completed_ids=_completed_module_ids(uid, curriculum),
            next_mod_id=next_mod.id if next_mod else None,
        ),
    )


async def cmd_review(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _touch_user(update)
    await _begin_review(update, context, _uid(update))


async def cmd_fact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _touch_user(update)
    streak = _meaningful(_uid(update))
    await update.effective_message.reply_text(
        _render_fact(_cur(context)),
        parse_mode="HTML",
        reply_markup=kb.after_fact(),
    )
    await _maybe_celebrate_streak(update, _uid(update), streak)


async def cmd_term(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _touch_user(update)
    if context.args:
        await _send_term(update, context, " ".join(context.args), as_new=True)
        return
    context.user_data["awaiting_term"] = True
    await update.effective_message.reply_text(
        GLOSSARY_PROMPT, parse_mode="HTML", reply_markup=kb.glossary_prompt()
    )


async def cmd_legal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _touch_user(update)
    await update.effective_message.reply_text(
        LEGAL, parse_mode="HTML", reply_markup=kb.back_menu()
    )


PAY_SUPPORT = (
    "<b>Payment support</b>\n"
    "Optional Stars tips go to the bot operator. For tip issues, message here "
    "with the approximate time of payment.\n\n"
    "Telegram Support cannot help with purchases made via this bot.\n"
    "Refunds (if needed) are handled by the bot owner per Telegram Stars rules.\n\n"
    "See also /legal. Content is free regardless of tips."
)


async def cmd_paysupport(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _touch_user(update)
    await update.effective_message.reply_text(
        PAY_SUPPORT, parse_mode="HTML", reply_markup=kb.back_menu()
    )


async def cmd_terms(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Telegram requires easy access to terms for Stars merchants."""
    await cmd_legal(update, context)


async def cmd_pro(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _touch_user(update)
    uid = _uid(update)
    await update.effective_message.reply_text(
        _pro_text(uid),
        parse_mode="HTML",
        reply_markup=kb.pro_menu(is_premium=prem.user_has_premium(uid)),
    )


async def cmd_buy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _touch_user(update)
    uid = _uid(update)
    if prem.user_has_premium(uid):
        await update.effective_message.reply_text(
            f"You’re already marked as a recent supporter.\n{prem.premium_status_line(uid)}\n\n"
            "All content stays free — thank you!",
            parse_mode="HTML",
            reply_markup=kb.back_menu(),
        )
        return
    try:
        await prem.send_premium_invoice(update, context)
    except Exception:
        log.exception("payment_invoice_failed user_id=%s", uid)
        await update.effective_message.reply_text(
            "Could not open the Stars invoice. Try again later or check BotFather payments settings.",
            reply_markup=kb.back_menu(),
        )


async def cmd_daily(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _touch_user(update)
    uid = _uid(update)
    arg = (context.args[0].lower() if context.args else "").strip()
    if arg in {"on", "1", "true", "yes"}:
        db.set_daily_opt_in(uid, True)
        msg = (
            "📅 Daily lessons <b>enabled</b>. "
            "You’ll get a short push around 09:00 UTC (configurable)."
        )
    elif arg in {"off", "0", "false", "no"}:
        db.set_daily_opt_in(uid, False)
        msg = "📅 Daily lessons <b>disabled</b>."
    else:
        state = "ON" if db.get_daily_opt_in(uid) else "OFF"
        msg = (
            f"Daily lesson is currently <b>{state}</b>.\n"
            "Usage: <code>/daily on</code> or <code>/daily off</code>"
        )
    await update.effective_message.reply_text(
        msg, parse_mode="HTML", reply_markup=_menu_markup(uid)
    )


async def cmd_certificate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _touch_user(update)
    user = update.effective_user
    assert user is not None
    text = certs.format_certificates_html(user.id, user.first_name)
    await update.effective_message.reply_text(
        text, parse_mode="HTML", reply_markup=kb.certs_menu()
    )
    clist = db.list_certificates(user.id)
    if clist:
        latest = clist[-1]
        png = certs.render_certificate_png(
            user.first_name, str(latest["title"]), str(latest["awarded_at"])
        )
        if png:
            await update.effective_message.reply_photo(
                photo=InputFile(png, filename=f"cert_{latest['module_id']}.png"),
                caption=f"🏅 {latest['title']}",
            )


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message or not update.effective_message.text:
        return
    _touch_user(update)
    text = update.effective_message.text.strip()
    awaiting = context.user_data.pop("awaiting_term", False)
    curriculum = _cur(context)
    if awaiting:
        await _send_term(update, context, text, as_new=True)
        return
    if text and not text.startswith("/") and len(text) <= 48 and curriculum.lookup_term(text):
        await _send_term(update, context, text, as_new=True)
        return
    await update.effective_message.reply_text(
        "Try /menu, /path, /review, /fact, or /term — for example "
        "<code>/term turbofan</code>.",
        parse_mode="HTML",
        reply_markup=_menu_markup(_uid(update)),
    )


async def _send_term(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    word: str,
    *,
    as_new: bool,
) -> None:
    curriculum = _cur(context)
    hit = curriculum.lookup_term(word)
    related = None
    if hit:
        key, defn = hit
        text = f"📖 <b>{html.escape(key)}</b>\n\n{rich(defn)}"
        related = curriculum.find_module_for_term(key)
    else:
        suggestions = curriculum.suggest_terms(word)
        extra = ""
        if suggestions:
            extra = "\nDid you mean: " + ", ".join(
                f"<code>{html.escape(s)}</code>" for s in suggestions
            )
        text = (
            f"No glossary entry for <b>{html.escape(word)}</b>.{extra}\n\n"
            "Try a shorter word, an acronym (VOR, ILS, FADEC), or browse modules."
        )
        related = curriculum.find_module_for_term(word)
    markup = kb.glossary_result(related_mod_id=related)
    if as_new:
        await update.effective_message.reply_text(
            text, parse_mode="HTML", reply_markup=markup
        )
    else:
        await _edit_or_reply(update, text, markup)


# --- callbacks ---------------------------------------------------------------


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    await query.answer()
    _touch_user(update)
    data = query.data or ""
    try:
        await _route_callback(update, context, data)
    except Exception:
        log.exception("Callback failed: %s", data)
        await _edit_or_reply(
            update,
            "Something went sideways. Tap the menu and try again.",
            kb.main_menu(),
        )


async def _route_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE, data: str
) -> None:
    curriculum = _cur(context)
    user_id = _uid(update)
    user = update.effective_user

    if data.startswith("ob:"):
        goal_key = data.split(":", 1)[1]
        label = GOAL_LABELS.get(goal_key, goal_key)
        db.set_goal_and_onboard(user_id, label)
        name = user.first_name if user else None
        text = (
            f"Great — goal saved: <b>{html.escape(label)}</b>.\n\n"
            f"{_welcome_body(user_id, name)}"
        )
        await _edit_or_reply(update, text, kb.welcome_cta())
        return

    if data == "m":
        name = user.first_name if user else None
        await _edit_or_reply(
            update, _welcome_body(user_id, name), _menu_markup(user_id)
        )
        return
    if data == "cont":
        await _smart_continue(update, context, user_id)
        return
    if data == "path":
        next_mod = _next_incomplete_module(user_id, curriculum)
        await _edit_or_reply(
            update,
            _render_path(user_id, curriculum),
            kb.path_menu(
                curriculum.modules,
                completed_ids=_completed_module_ids(user_id, curriculum),
                next_mod_id=next_mod.id if next_mod else None,
            ),
        )
        return
    if data == "rev":
        await _begin_review(update, context, user_id)
        return
    if data == "rvn":
        state = context.user_data.get("review") or {}
        state["idx"] = int(state.get("idx") or 0) + 1
        context.user_data["review"] = state
        await _show_review_question(update, context)
        return
    if data.startswith("rva:"):
        _, mod_id, idx_s, choice_s = data.split(":")
        await _grade_review(update, context, mod_id, int(idx_s), int(choice_s))
        return
    if data == "mods":
        await _edit_or_reply(
            update,
            "<b>Curriculum</b>\nSeven modules, beginner → intermediate. "
            "🆓 All free. Each has short lessons and a scored quiz.",
            kb.modules_menu(curriculum.modules, user_id),
        )
        return
    if data == "pr":
        await _edit_or_reply(
            update, _render_progress(user_id, curriculum), kb.back_menu()
        )
        return
    if data == "h":
        await _edit_or_reply(update, HELP, kb.back_menu())
        return
    if data == "legal":
        await _edit_or_reply(update, LEGAL, kb.back_menu())
        return
    if data == "fact":
        streak = _meaningful(user_id)
        await _edit_or_reply(update, _render_fact(curriculum), kb.after_fact())
        await _maybe_celebrate_streak(update, user_id, streak)
        return
    if data == "gl":
        context.user_data["awaiting_term"] = True
        await _edit_or_reply(update, GLOSSARY_PROMPT, kb.glossary_prompt())
        return
    if data == "certs":
        name = user.first_name if user else None
        await _edit_or_reply(
            update, certs.format_certificates_html(user_id, name), kb.certs_menu()
        )
        return
    if data == "pro":
        await _edit_or_reply(
            update,
            _pro_text(user_id),
            kb.pro_menu(is_premium=prem.user_has_premium(user_id)),
        )
        return
    if data == "buy":
        if prem.user_has_premium(user_id):
            await _edit_or_reply(
                update,
                f"You’re already a recent supporter.\n{prem.premium_status_line(user_id)}",
                kb.back_menu(),
            )
            return
        if update.effective_message:
            await update.effective_message.reply_text(
                "Opening optional Stars tip…", parse_mode="HTML"
            )
        try:
            await prem.send_premium_invoice(update, context)
        except Exception:
            log.exception("payment_invoice_failed user_id=%s", user_id)
            await _edit_or_reply(
                update,
                "Could not open the Stars invoice. Try /buy later.",
                kb.back_menu(),
            )
        return
    if data == "daily:tog":
        new_state = not db.get_daily_opt_in(user_id)
        db.set_daily_opt_in(user_id, new_state)
        label = "ON" if new_state else "OFF"
        name = user.first_name if user else None
        await _edit_or_reply(
            update,
            f"📅 Daily lesson is now <b>{label}</b>.\n\n{_welcome_body(user_id, name)}",
            _menu_markup(user_id),
        )
        return

    if data.startswith("md:"):
        mod = curriculum.by_id(data.split(":", 1)[1])
        if not mod:
            await _edit_or_reply(
                update, "Unknown module.", kb.modules_menu(curriculum.modules, user_id)
            )
            return
        await _show_module_home(update, context, mod, user_id)
        return

    if data.startswith("l:"):
        _, mod_id, idx_s = data.split(":")
        await _show_lesson(update, context, mod_id, int(idx_s), simple=False)
        return

    if data.startswith("e:"):
        _, mod_id, idx_s = data.split(":")
        await _show_lesson(update, context, mod_id, int(idx_s), simple=True)
        return

    if data.startswith("qz:"):
        mod_id = data.split(":", 1)[1]
        await _begin_quiz(update, context, mod_id)
        return

    if data.startswith("qn:"):
        _, mod_id, idx_s = data.split(":")
        await _show_quiz_question(update, context, mod_id, int(idx_s))
        return

    if data.startswith("qa:"):
        _, mod_id, idx_s, choice_s = data.split(":")
        await _grade_quiz(update, context, mod_id, int(idx_s), int(choice_s))
        return

    if data.startswith("qs:"):
        mod_id = data.split(":", 1)[1]
        await _show_quiz_score(update, context, mod_id)
        return

    await _edit_or_reply(update, "Unknown action. Returning to the menu.", _menu_markup(user_id))


async def _show_lesson(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    mod_id: str,
    idx: int,
    *,
    simple: bool,
) -> None:
    mod = _cur(context).by_id(mod_id)
    if not mod:
        await _edit_or_reply(update, "Unknown module.", kb.main_menu())
        return
    idx = max(0, min(idx, len(mod.lessons) - 1))
    uid = _uid(update)
    db.mark_lesson(uid, mod.id, idx)
    streak = _meaningful(uid)
    text = _render_lesson(mod, idx, simple=simple)
    markup = kb.simple_nav(mod, idx) if simple else kb.lesson_nav(mod, idx)
    await _edit_or_reply(update, text, markup)
    await _maybe_celebrate_streak(update, uid, streak)
    await _maybe_award_cert(update, uid, mod)


async def _begin_quiz(
    update: Update, context: ContextTypes.DEFAULT_TYPE, mod_id: str
) -> None:
    mod = _cur(context).by_id(mod_id)
    if not mod:
        await _edit_or_reply(update, "Unknown module.", kb.main_menu())
        return
    _start_quiz_state(context, mod_id)
    intro = (
        f"{mod.emoji} <b>{html.escape(mod.title)} quiz</b>\n\n"
        f"{len(mod.quizzes)} multiple-choice questions. "
        "You get immediate feedback and a short explanation after each answer.\n\n"
        "Question 1:"
    )
    item = mod.quizzes[0]
    text = (
        f"{intro}\n\n"
        f"<i>Question 1 of {len(mod.quizzes)}</i>\n\n"
        f"{html.escape(item.question)}"
    )
    await _edit_or_reply(update, text, kb.quiz_choices(mod.id, 0, item))


async def _show_quiz_question(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    mod_id: str,
    q_idx: int,
) -> None:
    mod = _cur(context).by_id(mod_id)
    if not mod:
        await _edit_or_reply(update, "Unknown module.", kb.main_menu())
        return
    state = _quiz_state(context)
    if state.get("mod") != mod_id:
        _start_quiz_state(context, mod_id)
        state = _quiz_state(context)
    if q_idx >= len(mod.quizzes):
        await _show_quiz_score(update, context, mod_id)
        return
    state["idx"] = q_idx
    await _edit_or_reply(
        update,
        _quiz_question_text(mod, q_idx),
        kb.quiz_choices(mod.id, q_idx, mod.quizzes[q_idx]),
    )


async def _grade_quiz(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    mod_id: str,
    q_idx: int,
    choice: int,
) -> None:
    mod = _cur(context).by_id(mod_id)
    if not mod or not (0 <= q_idx < len(mod.quizzes)):
        await _edit_or_reply(update, "That quiz is no longer available.", kb.main_menu())
        return
    state = _quiz_state(context)
    if state.get("mod") != mod_id:
        _start_quiz_state(context, mod_id)
        state = _quiz_state(context)

    answered: list[int] = list(state.get("answered") or [])
    if q_idx in answered:
        await update.callback_query.answer("Already answered.", show_alert=False)
        return

    item = mod.quizzes[q_idx]
    correct = choice == item.answer
    uid = _uid(update)
    if correct:
        state["score"] = int(state.get("score") or 0) + 1
        db.clear_wrong_answer(uid, mod.id, q_idx)
        verdict = "✅ <b>Correct</b>"
    else:
        db.record_wrong_answer(uid, mod.id, q_idx)
        letters = "ABCD"
        right = letters[item.answer] if item.answer < len(letters) else str(item.answer)
        verdict = f"❌ <b>Not quite</b> — the answer is <b>{right}</b>"
    answered.append(q_idx)
    state["answered"] = answered
    state["idx"] = q_idx

    last = q_idx >= len(mod.quizzes) - 1
    if last:
        state["finished"] = True
        db.record_quiz(uid, mod.id, int(state["score"]), len(mod.quizzes))
        streak = _meaningful(uid)
        await _maybe_celebrate_streak(update, uid, streak)

    text = (
        f"{mod.emoji} <b>{html.escape(mod.title)} quiz</b>\n"
        f"<i>Question {q_idx + 1} of {len(mod.quizzes)}</i>\n\n"
        f"{html.escape(item.question)}\n\n"
        f"{verdict}\n\n"
        f"{rich(item.explanation)}"
    )
    await _edit_or_reply(update, text, kb.quiz_next(mod.id, q_idx + 1, last=last))


async def _show_quiz_score(
    update: Update, context: ContextTypes.DEFAULT_TYPE, mod_id: str
) -> None:
    mod = _cur(context).by_id(mod_id)
    if not mod:
        await _edit_or_reply(update, "Unknown module.", kb.main_menu())
        return
    state = _quiz_state(context)
    total = len(mod.quizzes)
    score = int(state.get("score") or 0) if state.get("mod") == mod_id else 0
    uid = _uid(update)
    if state.get("mod") == mod_id and not state.get("finished"):
        db.record_quiz(uid, mod.id, score, total)
        state["finished"] = True
        streak = _meaningful(uid)
        await _maybe_celebrate_streak(update, uid, streak)

    ratio = score / total if total else 0
    if ratio == 1:
        comment = "Clean sheet. You could teach this module."
    elif ratio >= 0.8:
        comment = "Solid. Skim the misses and you are ready to move on."
    elif ratio >= 0.5:
        comment = "Good start. Re-read the lessons on the misses, then retry."
    else:
        comment = "Tough round. The lessons will make more sense the second pass."

    snap = db.progress_snapshot(uid)
    best = snap["best"].get(mod.id)
    best_line = f"Best so far: <b>{best[0]}/{best[1]}</b>" if best else ""

    text = (
        f"{mod.emoji} <b>{html.escape(mod.title)}</b>\n"
        f"<b>Quiz complete</b>\n\n"
        f"Score: <b>{score}/{total}</b>\n"
        f"{best_line}\n\n"
        f"{comment}"
    )
    await _edit_or_reply(update, text, kb.quiz_done(mod.id))
    await _maybe_award_cert(update, uid, mod)
