"""Optional Stars tips and legacy premium helpers. All content is free."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from telegram import LabeledPrice, Update
from telegram.ext import ContextTypes

from bot import db
from bot.config import (
    PREMIUM_DAYS,
    PREMIUM_DESCRIPTION,
    PREMIUM_PAYLOAD,
    PREMIUM_TITLE,
    premium_bypass_user_ids,
    premium_stars_price,
)

log = logging.getLogger(__name__)


def is_module_free(module_id: str) -> bool:
    """All modules are free."""
    _ = module_id
    return True


def user_has_premium(user_id: int) -> bool:
    if user_id in premium_bypass_user_ids():
        return True
    is_prem, until = db.raw_premium_flags(user_id)
    if not is_prem:
        return False
    if until is None:
        return True
    try:
        exp = datetime.fromisoformat(str(until))
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return exp > datetime.now(timezone.utc)
    except ValueError:
        return bool(is_prem)


def can_access_module(user_id: int, module_id: str) -> bool:
    """All modules are free; gate retained only for API compatibility."""
    _ = user_id, module_id
    return True


def premium_status_line(user_id: int) -> str:
    """Short status for welcome/progress — content is always free."""
    if user_id in premium_bypass_user_ids() or user_has_premium(user_id):
        return "💚 Thanks for supporting AvGeek Academy · <b>all modules free</b>"
    return "🆓 <b>Entirely free</b> · all 7 modules unlocked"


async def send_premium_invoice(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    chat = update.effective_chat
    if chat is None:
        return
    price = premium_stars_price()
    log.info(
        "payment_invoice user_id=%s chat_id=%s price_xtr=%s payload=%s",
        update.effective_user.id if update.effective_user else None,
        chat.id,
        price,
        PREMIUM_PAYLOAD,
    )
    await context.bot.send_invoice(
        chat_id=chat.id,
        title=PREMIUM_TITLE,
        description=PREMIUM_DESCRIPTION,
        payload=PREMIUM_PAYLOAD,
        currency="XTR",
        prices=[LabeledPrice(PREMIUM_TITLE, price)],
        provider_token="",  # required empty string for Telegram Stars
    )


async def on_precheckout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.pre_checkout_query
    if query is None:
        return
    ok = query.invoice_payload == PREMIUM_PAYLOAD
    log.info(
        "payment_precheckout user_id=%s ok=%s payload=%s currency=%s total=%s",
        query.from_user.id if query.from_user else None,
        ok,
        query.invoice_payload,
        query.currency,
        query.total_amount,
    )
    if ok:
        await query.answer(ok=True)
    else:
        await query.answer(ok=False, error_message="Unknown product. Please try /buy again.")


async def on_successful_payment(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    msg = update.effective_message
    user = update.effective_user
    if msg is None or user is None or msg.successful_payment is None:
        return
    payment = msg.successful_payment
    log.info(
        "payment_success user_id=%s currency=%s total=%s payload=%s charge_id=%s",
        user.id,
        payment.currency,
        payment.total_amount,
        payment.invoice_payload,
        payment.telegram_payment_charge_id,
    )
    if payment.invoice_payload != PREMIUM_PAYLOAD:
        log.error(
            "payment_unexpected_payload user_id=%s payload=%s",
            user.id,
            payment.invoice_payload,
        )
        await msg.reply_text(
            "Payment received but the product was unexpected. Contact support with your receipt."
        )
        return
    until = db.set_premium(user.id, days=PREMIUM_DAYS)
    await msg.reply_text(
        f"💚 <b>Thank you for the tip!</b>\n\n"
        f"AvGeek Academy stays free for everyone. Your support means a lot.\n"
        f"Supporter badge until <b>{until}</b>.\n\n"
        f"Keep learning — /path or /menu.",
        parse_mode="HTML",
    )
