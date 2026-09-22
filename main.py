"""
Entry point. Polls all active bookmakers concurrently, matches fixtures,
evaluates each for arbitrage, and alerts via Telegram â€” with a cooldown so
the same opportunity doesn't spam you every 30 seconds while it persists.

Run:
    python main.py
"""

import asyncio
import logging
import threading
import time

import config
from arbitrage import evaluate_fixture
from fetchers.base import OddsQuote
from fetchers.betking_fetcher import BetkingFetcher
from fetchers.naijabet_fetchers import Bet9jaFetcher, NairabetFetcher
from fixture_matcher import group_by_fixture
from health_server import start_health_server
from telegram_notifier import send_alert, send_status

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("arb_alert")

FETCHER_REGISTRY = {
    "bet9ja": Bet9jaFetcher,
    "nairabet": NairabetFetcher,
    "betking": BetkingFetcher,
}


def build_fetchers() -> list:
    fetchers = []
    for name in config.ACTIVE_BOOKMAKERS:
        cls = FETCHER_REGISTRY.get(name)
        if cls is None:
            logger.warning("No fetcher registered for bookmaker '%s' â€” skipping", name)
            continue
        try:
            fetchers.append(cls())
        except RuntimeError as e:
            logger.error("Could not initialize fetcher '%s': %s", name, e)
    return fetchers


async def fetch_all(fetchers, league: str) -> list[OddsQuote]:
    """Fetch odds from every bookmaker concurrently; a single bookmaker
    failing must not take down the whole poll cycle."""
    results = await asyncio.gather(
        *(f.fetch_odds(league) for f in fetchers), return_exceptions=True
    )
    quotes: list[OddsQuote] = []
    for fetcher, result in zip(fetchers, results):
        if isinstance(result, Exception):
            logger.warning("Fetch failed for %s/%s: %s", fetcher.name, league, result)
            continue
        quotes.extend(result)
    return quotes


async def poll_cycle(fetchers, alert_history: dict) -> None:
    for league in config.TRACKED_LEAGUES:
        quotes = await fetch_all(fetchers, league)
        if len(quotes) < 2:
            continue  # need at least 2 bookmakers' worth of data to compare

        groups = group_by_fixture(quotes, config.FIXTURE_MATCH_THRESHOLD)

        for group in groups:
            if len({q.bookmaker for q in group}) < 2:
                continue  # only one bookmaker has this fixture â€” nothing to arb against

            opp = evaluate_fixture(
                group,
                max_age_seconds=config.MAX_ODDS_AGE_SECONDS,
                min_profit_percent=config.MIN_PROFIT_PERCENT,
                reference_stake=config.REFERENCE_STAKE_NGN,
            )
            if opp is None:
                continue

            key = (opp.league, opp.home_team, opp.away_team)
            last_alerted = alert_history.get(key, 0)
            if time.time() - last_alerted < config.ALERT_COOLDOWN_SECONDS:
                continue

            logger.info(
                "Arb found: %s vs %s â€” %.2f%%",
                opp.home_team, opp.away_team, opp.profit_percent,
            )
            sent = await send_alert(config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID, opp)
            if sent:
                alert_history[key] = time.time()


async def main():
    # Start the health-check HTTP server in a background thread so Render
    # sees an open port and UptimeRobot has an endpoint to ping. This never
    # touches odds data â€” it's purely a liveness signal.
    threading.Thread(
        target=start_health_server, args=(config.PORT,), daemon=True
    ).start()

    fetchers = build_fetchers()
    if not fetchers:
        logger.error("No bookmaker fetchers available â€” check config and installed deps.")
        return

    logger.info("Starting arbitrage alert system with %d bookmaker(s): %s",
                len(fetchers), [f.name for f in fetchers])
    await send_status(
        config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID,
        f"âœ… Arb alert system started â€” watching {[f.name for f in fetchers]} "
        f"across {len(config.TRACKED_LEAGUES)} leagues, poll every {config.POLL_INTERVAL_SECONDS}s.",
    )

    alert_history: dict = {}
    while True:
        cycle_start = time.monotonic()
        try:
            await poll_cycle(fetchers, alert_history)
        except Exception:
            logger.exception("Unhandled error during poll cycle")

        elapsed = time.monotonic() - cycle_start
        sleep_for = max(0.0, config.POLL_INTERVAL_SECONDS - elapsed)
        await asyncio.sleep(sleep_for)


if __name__ == "__main__":
    asyncio.run(main())
