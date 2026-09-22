"""
Configuration for the Nigerian sports-betting arbitrage alert system.

Fill in the values marked TODO before running. Never commit real credentials â€”
use environment variables in production (os.environ.get(...)).
"""

import os

# --- Telegram ---
# Create a bot via @BotFather on Telegram, get the token.
# Get your chat_id by messaging your bot then hitting:
# https://api.telegram.org/bot<TOKEN>/getUpdates
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "TODO_YOUR_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "TODO_YOUR_CHAT_ID")

# --- Bookmakers to poll ---
# Only bookmakers with a working fetcher in fetchers/ will actually be used.
# Start with these three â€” they're the ones NaijaBet_Api supports natively.
ACTIVE_BOOKMAKERS = ["bet9ja", "nairabet", "betking"]

# --- Polling ---
POLL_INTERVAL_SECONDS = 30       # how often to re-fetch odds per bookmaker
FIXTURE_MATCH_THRESHOLD = 0.82   # min similarity (0-1) to treat two team names as the same match

# --- Arbitrage thresholds ---
# Minimum guaranteed profit % (after implied-probability math) to trigger an alert.
# Set conservatively at first â€” real Nigerian bookmaker margins are usually 5-8%,
# so genuine cross-book arbs above ~2% are uncommon and worth double-checking manually.
MIN_PROFIT_PERCENT = 1.5

# Max age (seconds) an odds quote can be before it's considered stale and excluded
# from arb calculations. This is the "accuracy" safeguard â€” a match built from a
# 40-second-old quote from one book and a fresh quote from another is not a real arb.
MAX_ODDS_AGE_SECONDS = 45

# Assumed stake you'd actually place, for the alert to show real Naira profit
# (not just a %). Purely illustrative â€” adjust per your bankroll.
REFERENCE_STAKE_NGN = 50_000

# Leagues to track (extend as needed â€” must match what each fetcher exposes)
TRACKED_LEAGUES = ["PREMIERLEAGUE", "LALIGA", "SERIEA", "BUNDESLIGA"]`

# --- Dedup ---
# Don't re-alert the same fixture+market within this window even if it keeps qualifying.
ALERT_COOLDOWN_SECONDS = 600

# --- Deployment (Render / UptimeRobot) ---
# Render sets $PORT itself for Web Services â€” the health check server binds
# to this so Render sees an open port and UptimeRobot has something to ping.
PORT = int(os.environ.get("PORT", 10000))
