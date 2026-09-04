# AvGeek Academy — launch checklist

## BotFather
- [ ] `/setname` AvGeek Academy
- [ ] `/setdescription` + `/setabouttext` from `growth/botfather.txt`
- [ ] `/setcommands` paste command list
- [ ] Profile photo set
- [ ] Stars / digital goods payments enabled for the bot
- [ ] Confirm username is `@AvGeekAcademyBot` (or update landing links)

## Env / deploy
- [ ] `.env` has `TELEGRAM_BOT_TOKEN` (never commit)
- [ ] Set `PREMIUM_STARS_PRICE` (default 150)
- [ ] Set `PREMIUM_BYPASS_USER_IDS` to your Telegram id for testing
- [ ] Choose polling (local) or `WEBHOOK_URL` + `PORT` + `WEBHOOK_PATH` (Railway/Fly)
- [ ] `DAILY_LESSON_HOUR=9` (UTC) or preferred hour
- [ ] Volume/persist `data/` so `progress.db` survives restarts
- [ ] Cron or one-off: `scripts/backup_db.sh`

## Content
- [ ] Confirm diagrams in `content/diagrams/{aero,struct,prop,avion,sys,nav,safe}.png`
- [ ] Spot-check one lesson + quiz per free module
- [ ] Spot-check locked Pro module shows upgrade CTA

## Product smoke test
- [ ] Fresh user: `/start` → goal buttons → welcome + disclaimer + Start Aerodynamics
- [ ] Returning user skips onboarding
- [ ] Streak increments on lesson/fact/quiz; shows on `/progress` + menu
- [ ] `/daily on` then verify job scheduling in logs
- [ ] Complete free module lessons + ≥80% quiz → certificate
- [ ] `/buy` invoice (XTR) → pre-checkout → successful_payment → Pro unlocked
- [ ] Bypass id gets Pro without paying
- [ ] `/legal` readable; welcome links to it

## Growth
- [ ] Host or share `landing/index.html`
- [ ] Create channel; schedule posts from `growth/channel_posts.md`
- [ ] Pin launch post with bot deep link

## Ops
- [ ] Structured logs show `payment_*` lines without printing the bot token
- [ ] README deploy notes followed for Railway or Fly
- [ ] Restart procedure documented for the host (see README)
