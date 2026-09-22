# Nigerian Sports Betting Arbitrage Alert System

Watches odds across Nigerian bookmakers and sends a Telegram alert when a
cross-bookmaker arbitrage opportunity appears (i.e. you could bet all
outcomes of a match across different books and profit regardless of result).

## What's real here, and what isn't

- **Odds data**: real, scraped from bookmaker sites via the open-source
  [`NaijaBet_Api`](https://github.com/jayteealao/NaijaBet_Api) library â€”
  Bet9ja and NairaBet directly, BetKing via a headless browser (Playwright)
  because it's behind Cloudflare. Not simulated.
- **Coverage gap**: SportyBet, MSport, Betway Nigeria, and 1xBet have no
  working fetcher yet â€” there's no public API and no maintained scraper for
  them that I could verify. The `fetchers/` package is built so you (or I,
  in a follow-up) can add one per bookmaker without touching anything else.
- **The math**: standard 1X2 arbitrage â€” implied probability sum across the
  best available price per outcome. If it's under 100%, the split-stake
  guarantees profit *at the odds shown, if you can actually place all three
  bets before they move*.
- **What this system can't guarantee**: that the odds are still live by the
  time you act, that you're not stake-limited on the book with the best
  price, or that scraping a given bookmaker doesn't run afoul of its Terms
  of Service. Bookmakers routinely limit or close accounts they identify as
  arbing â€” that's a business/account risk this software has no way to
  eliminate, only to flag.

## Setup â€” local

```bash
pip install -r requirements.txt
playwright install chromium   # only needed for the BetKing fetcher

export TELEGRAM_BOT_TOKEN="your_token_from_botfather"
export TELEGRAM_CHAT_ID="your_chat_id"

python main.py
```

## Setup â€” Render + UptimeRobot

This system scrapes bookmaker sites directly (via `NaijaBet_Api`) rather than
calling a paid, rate-limited odds API â€” so there's no request quota to run
out of the way a service like The Odds API would impose. That's the main
reason this replaces an earlier attempt that used The Odds API: that API
also doesn't cover Nigerian bookmakers at all, only UK/EU ones.

1. Push this folder to a GitHub repo.
2. On Render: **New â†’ Web Service**, connect the repo.
   - Build command: `pip install -r requirements.txt && playwright install --with-deps chromium`
   - Start command: `python main.py` (also set via the included `Procfile`)
3. Set environment variables in Render's dashboard: `TELEGRAM_BOT_TOKEN`,
   `TELEGRAM_CHAT_ID`. Render sets `PORT` itself â€” don't override it.
4. Once deployed, Render gives you a URL like `https://your-app.onrender.com`.
   The health server responds `200 OK` on `/` â€” that's what confirms the
   process is alive, separate from whether any arbs have been found yet.
5. In UptimeRobot, add an HTTP(s) monitor pointed at that URL, checking every
   5 minutes. This keeps a free-tier Render service from spinning down due
   to inactivity â€” Render's health server has nothing to do with your odds
   data, it exists purely so Render/UptimeRobot see the app as "up".

**Playwright on Render**: the BetKing fetcher launches a real Chromium
browser, which needs system libraries Render's default build doesn't
include. Use `playwright install --with-deps chromium` in the build command
(not just `playwright install`), or BetKing fetches will fail on deploy even
though they work locally. This is also why `curl_cffi` is worth finishing
(see "Known rough edges" below) â€” it avoids the Chromium install entirely,
which means a lighter, faster Render build once BetKing's real endpoint is
captured.

Get a bot token from [@BotFather](https://t.me/BotFather) on Telegram.
Get your chat ID by messaging your new bot once, then visiting
`https://api.telegram.org/bot<TOKEN>/getUpdates` and reading the `chat.id`
field.

## Before you trust an alert

1. Every alert shows how stale (in seconds) the oldest odds quote it used
   was â€” the shorter, the more trustworthy.
2. Open all bookmakers involved and re-check the price before staking.
   `MIN_PROFIT_PERCENT` in `config.py` is intentionally conservative (1.5%)
   to leave margin for the odds having moved slightly.
3. Confirm none of your accounts on the relevant books are already stake-
   limited â€” a "guaranteed profit" alert is worthless if the bookmaker won't
   let you place a meaningful stake.

## Known rough edges to fix before relying on this for real money

- `betking_cffi_fetcher.py` is a **scaffold, not a working fetcher** â€”
  `BETKING_ODDS_ENDPOINT` is a placeholder. To finish it: open BetKing in a
  browser, capture the real odds request from DevTools â†’ Network, and send
  me the URL + a sample response so the parsing matches reality. Until then,
  `main.py` uses the Playwright-based `BetkingFetcher`, which is the one
  confirmed to work.
- Fixture matching (`fixture_matcher.py`) uses fuzzy string similarity on
  team names, which is a real source of false positives/negatives. If you
  see incorrect fixture pairings, replace it with an explicit alias table
  per bookmaker rather than tuning the threshold.
- BetKing polling is much slower (real browser launch per fetch) â€” with 5
  leagues and a 30s poll interval this may not keep up. Consider polling
  BetKing on a longer interval than the others, or running it in parallel
  with its own scheduler.
- No persistence â€” alert cooldown state is in-memory only, so a restart
  clears it and you may get a duplicate alert for a still-live opportunity.
- No handling yet for bookmakers going offline, rate-limiting scrapers, or
  CAPTCHA challenges â€” those will surface as fetch exceptions in the logs,
  worth alerting on separately (e.g. a Telegram message if a bookmaker fails
  N consecutive polls).
