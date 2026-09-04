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
from bot.config import FREE_MODULE_IDS, premium_stars_price
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


def _welcome_body(user_id: int, first_name: str | None = None) -> str:
    name = html.escape((first_name or "").strip())
    hello = f"Hi {name}!\n\n" if name else ""
    streak = db.get_streak(user_id)
    streak_bit = f"🔥 Streak: <b>{streak}</b> day{'s' if streak != 1 else ''}\n" if streak else ""
    return (
        f"{hello}"
        f"<b>AvGeek Academy</b>\n"
        f"{streak_bit}"
        "Learn how aircraft fly, how they are built, and how crews navigate the sky.\n\n"
        "Lessons are short. Use <b>Next</b>, <b>Explain simpler</b>, or jump into a "
        "<b>quiz</b> whenever you feel ready.\n\n"
        f"{DISCLAIMER_ONE_LINER}\n\n"
        f"{prem.premium_status_line(user_id)}\n\n"
        "Pick a path:"
    )


HELP = (
    "<b>Commands</b>\n"
    "/start — welcome and main menu\n"
    "/menu — jump back to the main menu\n"
    "/help — this message\n"
    "/progress — lessons, quiz scores, streak\n"
    "/fact — a random aviation fact\n"
    "/term &lt;word&gt; — look up a glossary term\n"
    "/daily on|off — daily lesson push (~09:00 UTC)\n"
    "/certificate — view earned certificates\n"
    "/pro — AvGeek Pro details\n"
    "/buy — unlock Pro with Telegram Stars\n"
    "/legal — disclaimer, terms, privacy\n\n"
    "<b>How to learn</b>\n"
    "Open a module, read the lessons in order, then take the quiz. "
    "Score ≥80% with all lessons done to earn a certificate.\n\n"
    "<b>Free vs Pro</b>\n"
    "Free: Aerodynamics + Structures. "
    "Pro unlocks the full curriculum via Telegram Stars.\n\n"
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
    "airworthiness decisions. We may change curriculum or pricing. Telegram Stars "
    "purchases follow Telegram’s payment rules; Pro access is time-limited as stated "
    "at purchase.\n\n"
    "<b>Privacy</b>\n"
    "We store: Telegram user id, optional username/first name, learning progress, "
    "optional goal, streak dates, daily opt-in, premium status, and certificates. "
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


def _meaningful(user_id: int) -> None:
    db.touch_streak(user_id)


def _menu_markup(user_id: int) -> Any:
    return kb.main_menu(
        daily_on=db.get_daily_opt_in(user_id),
        streak=db.get_streak(user_id),
    )


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
            # Can't edit a photo caption into long HTML text — send new message.
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
    lock = ""
    if not prem.can_access_module(user_id, mod.id):
        lock = "\n🔒 <b>Pro module</b> — unlock with Telegram Stars.\n"
    return (
        f"{mod.emoji} <b>{html.escape(mod.title)}</b>\n\n"
        f"{rich(mod.blurb)}\n"
        f"{lock}\n"
        f"Lessons: <b>{len(seen)}/{len(mod.lessons)}</b> read · "
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
    lines = [
        "<b>Your progress</b>\n",
        f"🔥 Streak: <b>{streak}</b> day{'s' if streak != 1 else ''}\n",
        f"{prem.premium_status_line(user_id)}\n",
    ]
    total_lessons = 0
    done_lessons = 0
    for mod in curriculum.modules:
        total_lessons += len(mod.lessons)
        n = snap["lessons"].get(mod.id, 0)
        done_lessons += n
        best = snap["best"].get(mod.id)
        quiz_bit = f" · quiz best {best[0]}/{best[1]}" if best else " · quiz —"
        bar = "●" * n + "○" * (len(mod.lessons) - n)
        lock = "" if prem.can_access_module(user_id, mod.id) else " 🔒"
        lines.append(
            f"{mod.emoji} <b>{html.escape(mod.title)}</b>{lock}\n"
            f"    {bar}  {n}/{len(mod.lessons)} lessons{quiz_bit}"
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
        lines.append("\nNothing saved yet — open a module and start a lesson.")
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
    free = ", ".join(sorted(FREE_MODULE_IDS))
    status = prem.premium_status_line(user_id)
    return (
        f"<b>AvGeek Pro</b>\n\n"
        f"{status}\n\n"
        f"<b>Free modules:</b> <code>{free}</code> (Aerodynamics, Structures).\n"
        f"<b>Pro unlocks:</b> Propulsion, Avionics, Systems, Navigation/ATC, Safety "
        f"&amp; emerging tech — plus the full certificate track.\n\n"
        f"<b>Price:</b> {price} Telegram Stars for 30 days "
        f"(“AvGeek Pro — 30 days”).\n\n"
        "Tap <b>Buy</b> or send /buy to pay with Stars."
    )


async def _maybe_award_cert(
    update: Update, user_id: int, mod: Module
) -> None:
    awarded = db.try_award_certificate(
        user_id, mod.id, mod.title, len(mod.lessons)
    )
    if not awarded or not update.effective_message:
        return
    name = update.effective_user.first_name if update.effective_user else None
    text = (
        f"🏅 <b>Certificate earned!</b>\n\n"
        f"You completed <b>{html.escape(mod.title)}</b> with a quiz best of at least 80%.\n"
        f"View all with /certificate"
    )
    await update.effective_message.reply_text(text, parse_mode="HTML")
    png = None
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
    if not prem.can_access_module(user_id, mod.id):
        text = (
            f"🔒 <b>{html.escape(mod.title)}</b>\n\n"
            f"{rich(mod.blurb)}\n\n"
            "This module is part of <b>AvGeek Pro</b>. "
            "Free learners can study Aerodynamics and Structures.\n\n"
            f"{_pro_text(user_id)}"
        )
        await _edit_or_reply(update, text, kb.upgrade_cta(mod.title))
        return

    seen = db.lessons_done(user_id, mod.id)
    overview = _module_overview(mod, user_id)
    diagram = diagram_path(mod.id)
    markup = kb.module_home(mod, len(seen))

    # Prefer sending diagram as a fresh photo when available.
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


async def cmd_fact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _touch_user(update)
    _meaningful(_uid(update))
    await update.effective_message.reply_text(
        _render_fact(_cur(context)),
        parse_mode="HTML",
        reply_markup=kb.after_fact(),
    )


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
    "For issues with AvGeek Pro / Stars purchases, message the bot owner from this chat "
    "(reply here describing the problem and include the approximate time of payment).\n\n"
    "Telegram Support cannot help with purchases made via this bot.\n"
    "Refunds (if needed) are handled by the bot owner per Telegram Stars rules.\n\n"
    "See also /legal."
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
            f"You already have Pro.\n{prem.premium_status_line(uid)}",
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
    # Optionally attach PNG for the latest cert
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
        "Try /menu, /fact, or /term followed by a word — for example "
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
    if hit:
        key, defn = hit
        text = f"📖 <b>{html.escape(key)}</b>\n\n{rich(defn)}"
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
    markup = kb.glossary_prompt()
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
            f"{_welcome_body(user_id, name)}\n\n"
            "Ready when you are:"
        )
        await _edit_or_reply(update, text, kb.welcome_cta())
        return

    if data == "m":
        name = user.first_name if user else None
        await _edit_or_reply(
            update, _welcome_body(user_id, name), _menu_markup(user_id)
        )
        return
    if data == "mods":
        await _edit_or_reply(
            update,
            "<b>Curriculum</b>\nSeven modules, beginner → intermediate. "
            "🆓 Free: Aerodynamics + Structures. ⭐ Pro unlocks the rest.\n"
            "Each has short lessons and a scored quiz.",
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
        _meaningful(user_id)
        await _edit_or_reply(update, _render_fact(curriculum), kb.after_fact())
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
                f"You already have Pro.\n{prem.premium_status_line(user_id)}",
                kb.back_menu(),
            )
            return
        # Invoices must be new messages
        if update.effective_message:
            await update.effective_message.reply_text(
                "Opening Stars checkout…", parse_mode="HTML"
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


async def _ensure_module_access(
    update: Update, user_id: int, mod: Module
) -> bool:
    if prem.can_access_module(user_id, mod.id):
        return True
    await _edit_or_reply(
        update,
        f"🔒 <b>{html.escape(mod.title)}</b> is a Pro module.\n\n{_pro_text(user_id)}",
        kb.upgrade_cta(mod.title),
    )
    return False


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
    if not await _ensure_module_access(update, _uid(update), mod):
        return
    idx = max(0, min(idx, len(mod.lessons) - 1))
    uid = _uid(update)
    db.mark_lesson(uid, mod.id, idx)
    _meaningful(uid)
    text = _render_lesson(mod, idx, simple=simple)
    markup = kb.simple_nav(mod, idx) if simple else kb.lesson_nav(mod, idx)
    await _edit_or_reply(update, text, markup)
    await _maybe_award_cert(update, uid, mod)


async def _begin_quiz(
    update: Update, context: ContextTypes.DEFAULT_TYPE, mod_id: str
) -> None:
    mod = _cur(context).by_id(mod_id)
    if not mod:
        await _edit_or_reply(update, "Unknown module.", kb.main_menu())
        return
    if not await _ensure_module_access(update, _uid(update), mod):
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
    if not await _ensure_module_access(update, _uid(update), mod):
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
    if not await _ensure_module_access(update, _uid(update), mod):
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
    if correct:
        state["score"] = int(state.get("score") or 0) + 1
        verdict = "✅ <b>Correct</b>"
    else:
        letters = "ABCD"
        right = letters[item.answer] if item.answer < len(letters) else str(item.answer)
        verdict = f"❌ <b>Not quite</b> — the answer is <b>{right}</b>"
    answered.append(q_idx)
    state["answered"] = answered
    state["idx"] = q_idx

    last = q_idx >= len(mod.quizzes) - 1
    if last:
        state["finished"] = True
        uid = _uid(update)
        db.record_quiz(uid, mod.id, int(state["score"]), len(mod.quizzes))
        _meaningful(uid)

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
        _meaningful(uid)

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

