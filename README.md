# AvGeek Academy (Aviation Tutor Bot)

Interactive Telegram bot that teaches aviation technology — aerodynamics, structures, propulsion, avionics, systems, navigation/ATC, and safety / emerging tech.

**Bot:** [https://t.me/AvGeekAcademyBot](https://t.me/AvGeekAcademyBot)

**Entirely free** — all 7 modules unlocked for every learner. Optional Telegram Stars tips support the project; never required for content.

Aimed at curious beginners through intermediate learners. Lessons are short; every module has a scored multiple-choice quiz. Progress is stored in SQLite, keyed by Telegram user id.

This is **not** a ground school, type rating, or operational manual. See `/legal` in the bot.

## Features

- Onboarding (goal) on first `/start`, short welcome + disclaimer
- Seven curriculum modules with lessons, quizzes, and diagrams
- **Learning path** (`/path`) — roadmap with checkmarks, % complete, “You are here”
- **Smart Continue** — jumps to the next unread lesson across the curriculum
- **Spaced review** (`/review`) — 3-question drill from misses / finished modules
- Streaks with celebrations at 3 / 7 / 14 days; module-complete celebrations + certificates
- Progress bars, reviews-due count, overall %
- Glossary with related-module deep link
- Optional Stars tip (`/buy` / `/pro`) — support only, not a paywall
- `/legal` disclaimer, terms, privacy
- Polling or webhook mode

## Free forever

| Access | Notes |
| --- | --- |
| All modules | Unlocked for every user |
| Optional tip | Telegram Stars via `/buy` — clearly labeled optional support |

- Tip invoice uses `currency="XTR"` (Stars). Price from env `PREMIUM_STARS_PRICE` (default **150**).
- Payload: `premium_30d` (legacy id; grants a “supporter” window, not content locks).
- `PREMIUM_BYPASS_USER_IDS` still marks those ids as supporters without paying.

## Project layout

```
aviation-tutor-bot/
├── bot/                  Application package
│   ├── main.py           Entry (polling or webhook)
│   ├── handlers.py       Commands + callbacks
│   ├── premium.py        Optional Stars tip helpers
│   ├── certificates.py   HTML + optional PNG
│   ├── daily.py          JobQueue daily lesson
│   ├── db.py             SQLite + migrations
│   └── …
├── content/
│   ├── modules/          YAML curriculum
│   ├── diagrams/         module_id.png
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
path - Learning roadmap
review - Spaced review drill
help - Commands and how to learn
progress - Bars, streak, reviews due
fact - A random aviation fact
term - Look up a glossary term
daily - Daily lesson on|off
certificate - View earned certificates
pro - Free bot info + optional tip
buy - Optional tip via Stars
legal - Disclaimer, terms, privacy
```

Enable Stars / digital-goods payments only if you want optional tips.

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

1. Stop the old process (Ctrl+C, or your process manager / Render redeploy).
2. `cd` to the project root, ensure `.venv` and `.env` are in place.
3. `python -m bot` (or restart the container/service).

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

## Deploy notes (Render / Railway / Fly)

1. Set env vars from `.env.example` (token, optional Stars tip price, optional bypass ids).
2. For webhook: set public `WEBHOOK_URL`; set `PORT` if needed; keep `WEBHOOK_PATH=/telegram`.
3. Persist `/app/data` (volume) so progress survives redeploys.
4. After deploy, message `/start` and run through `growth/launch_checklist.md`.

## Landing page

Open `landing/index.html` in a browser or host it on any static site. Links to https://t.me/AvGeekAcademyBot.

## Diagrams

Place images at `content/diagrams/<module_id>.png` (or `.jpg`). See `content/diagrams/README.md`.

## License / content note

Original tutorial text for education. Teaching aid only — not official regulatory material. Always defer to the AFM, your CAA, and current charts.
