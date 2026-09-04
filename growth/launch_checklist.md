# AvGeek Academy — launch checklist

## BotFather
- [ ] `/setname` AvGeek Academy
- [ ] `/setdescription` + `/setabouttext` from `growth/botfather.txt` (FREE messaging)
- [ ] `/setcommands` paste command list (includes path, review)
- [ ] Profile photo set
- [ ] Stars / digital goods payments enabled only if offering optional tips
- [ ] Confirm username is `@AvGeekAcademyBot` (or update landing links)

## Env / deploy
- [ ] `.env` has `TELEGRAM_BOT_TOKEN` (never commit)
- [ ] Optional: `PREMIUM_STARS_PRICE` for tip amount (default 150)
- [ ] Optional: `PREMIUM_BYPASS_USER_IDS` for supporter badge testing
- [ ] Choose polling (local) or `WEBHOOK_URL` + `PORT` + `WEBHOOK_PATH` (Render)
- [ ] `DAILY_LESSON_HOUR=9` (UTC) or preferred hour
- [ ] Volume/persist `data/` so `progress.db` survives restarts
- [ ] Cron or one-off: `scripts/backup_db.sh`

## Content
- [ ] Confirm diagrams in `content/diagrams/{aero,struct,prop,avion,sys,nav,safe}.png`
- [ ] Spot-check one lesson + quiz per module (all unlocked)
- [ ] Confirm no lock / upgrade CTA on module browse

## Product smoke test
- [ ] Fresh user: `/start` → goal buttons → short welcome + Continue / Path
- [ ] `/path` shows checkmarks + You are here; Continue opens next unread lesson
- [ ] `/review` drills misses or practice; wrong answers stored
- [ ] Streak celebrations at 3/7/14 (once each via milestones_json)
- [ ] Module complete celebration + certificate CTA at ≥80%
- [ ] `/progress` shows text bars, streak, reviews due, overall %
- [ ] Glossary result offers Related lesson when matched
- [ ] `/pro` / `/buy` labeled optional tip; content free without paying
- [ ] `/legal` readable

## Growth
- [ ] Host or share `landing/index.html` (FREE messaging)
- [ ] Create channel; schedule posts from `growth/channel_posts.md`
- [ ] Pin launch post with bot deep link

## Ops
- [ ] Structured logs show `payment_*` lines without printing the bot token
- [ ] README deploy notes followed
- [ ] Restart procedure documented for the host (see README)
