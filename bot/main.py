"""Entry point: `python -m bot` or `python bot/main.py` from the project root."""

from __future__ import annotations

import logging
import sys
from datetime import time as dt_time
from pathlib import Path
from zoneinfo import ZoneInfo

# Allow `python bot/main.py` (in addition to `python -m bot`).
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from telegram.ext import (  # noqa: E402
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    PreCheckoutQueryHandler,
    filters,
)

from bot.config import (  # noqa: E402
    daily_lesson_hour,
    listen_port,
    telegram_token,
    webhook_path,
    webhook_url,
)
from bot.content_loader import load_curriculum  # noqa: E402
from bot.daily import daily_lesson_job  # noqa: E402
from bot.db import init_db  # noqa: E402
from bot.handlers import (  # noqa: E402
    cmd_buy,
    cmd_certificate,
    cmd_daily,
    cmd_fact,
    cmd_help,
    cmd_legal,
    cmd_paysupport,
    cmd_path,
    cmd_review,
    cmd_terms,
    cmd_menu,
    cmd_pro,
    cmd_progress,
    cmd_start,
    cmd_term,
    on_callback,
    on_text,
)
from bot.premium import on_precheckout, on_successful_payment  # noqa: E402

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("aviation-tutor")

# Keep httpx / telegram noisy internals quieter.
logging.getLogger("httpx").setLevel(logging.WARNING)


def build_app(token: str) -> Application:
    curriculum = load_curriculum()
    init_db()

    app = Application.builder().token(token).build()
    app.bot_data["curriculum"] = curriculum

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("progress", cmd_progress))
    app.add_handler(CommandHandler("path", cmd_path))
    app.add_handler(CommandHandler("review", cmd_review))
    app.add_handler(CommandHandler("fact", cmd_fact))
    app.add_handler(CommandHandler("term", cmd_term))
    app.add_handler(CommandHandler("legal", cmd_legal))
    app.add_handler(CommandHandler("terms", cmd_terms))
    app.add_handler(CommandHandler("paysupport", cmd_paysupport))
    app.add_handler(CommandHandler("pro", cmd_pro))
    app.add_handler(CommandHandler("buy", cmd_buy))
    app.add_handler(CommandHandler("daily", cmd_daily))
    app.add_handler(CommandHandler("certificate", cmd_certificate))
    app.add_handler(CommandHandler("certificates", cmd_certificate))

    app.add_handler(PreCheckoutQueryHandler(on_precheckout))
    app.add_handler(
        MessageHandler(filters.SUCCESSFUL_PAYMENT, on_successful_payment)
    )

    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    # Daily lesson job (~09:00 UTC by default).
    if app.job_queue is not None:
        hour = daily_lesson_hour()
        app.job_queue.run_daily(
            daily_lesson_job,
            time=dt_time(hour=hour, minute=0, tzinfo=ZoneInfo("UTC")),
            name="daily_lesson",
        )
        log.info("Scheduled daily lesson job at %02d:00 UTC", hour)
    else:
        log.warning(
            "JobQueue unavailable — install python-telegram-bot[job-queue] for daily lessons"
        )

    return app


def main() -> None:
    token = telegram_token()
    curriculum = load_curriculum()
    log.info(
        "Loaded %d modules, %d facts, %d glossary terms",
        len(curriculum.modules),
        len(curriculum.facts),
        len(curriculum.glossary),
    )
    app = build_app(token)
    wh = webhook_url()
    if wh:
        path = webhook_path()
        port = listen_port()
        full_url = f"{wh}{path}"
        log.info("Starting webhook on 0.0.0.0:%s path=%s url=%s", port, path, full_url)
        _run_webhook_with_health(app, port=port, path=path, full_url=full_url)
    else:
        log.info("Starting polling. Press Ctrl+C to stop.")
        app.run_polling(drop_pending_updates=True)


def _run_webhook_with_health(
    app: Application, *, port: int, path: str, full_url: str
) -> None:
    """Serve Telegram webhook + GET /health on the same port (Render-friendly)."""
    import asyncio

    from aiohttp import web
    from telegram import Update

    async def health(_request: web.Request) -> web.Response:
        return web.Response(text="ok")

    async def telegram_hook(request: web.Request) -> web.Response:
        data = await request.json()
        update = Update.de_json(data, app.bot)
        await app.update_queue.put(update)
        return web.Response(text="ok")

    async def runner() -> None:
        await app.initialize()
        await app.start()
        aio = web.Application()
        async def root(_request: web.Request) -> web.Response:
            return web.Response(
                text="AvGeek Academy bot is running. Open https://t.me/AvGeekAcademyBot",
                content_type="text/plain",
            )

        aio.router.add_get("/", root)
        aio.router.add_get("/health", health)
        route = "/" + path.lstrip("/")
        aio.router.add_post(route, telegram_hook)
        app_runner = web.AppRunner(aio)
        await app_runner.setup()
        site = web.TCPSite(app_runner, "0.0.0.0", port)
        await site.start()
        await app.bot.set_webhook(url=full_url, drop_pending_updates=True)
        log.info("Webhook + /health listening")
        # Block forever
        await asyncio.Event().wait()

    asyncio.run(runner())


if __name__ == "__main__":
    main()
