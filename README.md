# AvGeek Academy (Aviation Tutor Bot)

Interactive Telegram bot that teaches aviation technology — aerodynamics, structures, propulsion, avionics, systems, navigation/ATC, and safety / emerging tech.

**Bot:** [https://t.me/AvGeekAcademyBot](https://t.me/AvGeekAcademyBot)

Aimed at curious beginners through intermediate learners. Lessons are short; every module has a scored multiple-choice quiz. Progress is stored in SQLite, keyed by Telegram user id.

This is **not** a ground school, type rating, or operational manual. See `/legal` in the bot.

## Features

- Onboarding (goal) on first `/start`, polished welcome + disclaimer + CTA
- Seven curriculum modules with lessons, quizzes, and optional diagrams
- Streaks, daily lesson push (`/daily on|off`, ~09:00 UTC)
- Certificates when all lessons done and quiz best ≥ 80%
- Freemium: free `aero` + `struct`; other modules via **AvGeek Pro** (Telegram Stars)
- `/legal` disclaimer, terms, privacy
- Polling or webhook mode

## Freemium & Telegram Stars

| Plan | Access |
| --- | --- |
| Free | Modules `aero`, `struct` |
| AvGeek Pro — 30 days | All modules |

- Buy with `/buy` or the Pro menu. Invoice uses `currency="XTR"` (Stars).
- Price from env `PREMIUM_STARS_PRICE` (default **150**).
- Payload: `premium_30d`. Handlers: `PreCheckoutQueryHandler` + successful payment.
- Dev escape hatch: `PREMIUM_BYPASS_USER_IDS` (comma-separated Telegram ids) always get Pro.

## Project layout

```
aviation-tutor-bot/
├── bot/                  Application package
│   ├── main.py           Entry (polling or webhook)
│   ├── handlers.py       Commands + callbacks
│   ├── premium.py        Stars invoice + gates
│   ├── certificates.py   HTML + optional PNG
│   ├── daily.py          JobQueue daily lesson
│   ├── db.py             SQLite + migrations
│   └── …
├── content/
│   ├── modules/          YAML curriculum
│   ├── diagrams/         module_id.png (do not overwrite casually)
│   ├── facts.yaml
│   └── glossary.yaml
├── data/                 progress.db (+ backups/)
├── scripts/backup_db.sh
├── landing/index.html    Marketing page
├── growth/               BotFather copy, posts, checklist
├── .env.example
├── requirements.txt
└── Dockerfile
```

## BotFather setup

See `growth/botfather.txt` for description, about, and commands. Quick commands list:

```
start - Welcome and main menu
menu - Open the main menu
help - Commands and how to learn
progress - Lessons, quizzes, streak
fact - A random aviation fact
term - Look up a glossary term
daily - Daily lesson on|off
certificate - View earned certificates
pro - AvGeek Pro details
buy - Unlock Pro with Stars
legal - Disclaimer, terms, privacy
```

Enable Stars / digital-goods payments for the bot per current Telegram docs.

## Install and run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# set TELEGRAM_BOT_TOKEN (never commit .env)
```

**Polling (default):**

```bash
python -m bot
```

**Webhook** — set in `.env`:

```
WEBHOOK_URL=https://your-app.example.com
PORT=8080
WEBHOOK_PATH=/telegram
```

Then `python -m bot` listens on `PORT` and registers `WEBHOOK_URL + WEBHOOK_PATH`.

Do not print or log the bot token.

### Restart

1. Stop the old process (Ctrl+C, or your process manager / Railway / Fly redeploy).
2. `cd` to the project root, ensure `.venv` and `.env` are in place.
3. `python -m bot` (or restart the container/service).

If a PID still holds old code in memory, a restart is required to load file changes — editing files alone does not hot-reload a running process.

### Backup

```bash
./scripts/backup_db.sh
```

Copies `data/progress.db` → `data/backups/progress_<UTC timestamp>.db`.

## Docker

```bash
docker build -t avgeek-academy .
docker run --rm -e TELEGRAM_BOT_TOKEN='…' -p 8080:8080 \
  -v avgeek-data:/app/data avgeek-academy
```

`EXPOSE 8080` supports webhook hosts that inject `PORT`.

## Deploy notes (Railway / Fly)

1. Set env vars from `.env.example` (token, Stars price, optional bypass ids).
2. For webhook: set public `WEBHOOK_URL` to the service HTTPS URL; set `PORT` if the platform does not inject it; keep `WEBHOOK_PATH=/telegram` (or match your proxy).
3. Persist `/app/data` (volume) so progress and certificates survive redeploys.
4. Health: process should log module load counts, then either `Starting polling` or `Starting webhook…`.
5. After deploy, message `/start` and run through `growth/launch_checklist.md`.

## Landing page

Open `landing/index.html` in a browser or host it on any static site. Links to https://t.me/AvGeekAcademyBot.

## Diagrams

Place images at `content/diagrams/<module_id>.png` (or `.jpg`). Wired via `diagram_path()` and sent when opening a module home. See `content/diagrams/README.md`.

## License / content note

Original tutorial text for education. Teaching aid only — not official regulatory material. Always defer to the AFM, your CAA, and current charts.
