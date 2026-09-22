"""
Sends alerts via the Telegram Bot API using `requests`. Since `requests` is
synchronous and the rest of the system runs on asyncio, calls are wrapped in
asyncio.to_thread so a slow/hanging Telegram request can't stall the poll
loop for every bookmaker fetch behind it.
"""

import asyncio
import logging

import requests

from arbitrage import ArbOpportunity

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def format_alert(opp: ArbOpportunity) -> str:
    return (
        f"ðŸŽ¯ *Arbitrage opportunity â€” {opp.profit_percent:.2f}% guaranteed*\n\n"
        f"*{opp.home_team} vs {opp.away_team}* ({opp.league})\n\n"
        f"Home: *{opp.best_home.bookmaker}* @ {opp.best_home.odds_home:.2f} "
        f"â†’ stake â‚¦{opp.stake_home:,.0f}\n"
        f"Draw: *{opp.best_draw.bookmaker}* @ {opp.best_draw.odds_draw:.2f} "
        f"â†’ stake â‚¦{opp.stake_draw:,.0f}\n"
        f"Away: *{opp.best_away.bookmaker}* @ {opp.best_away.odds_away:.2f} "
        f"â†’ stake â‚¦{opp.stake_away:,.0f}\n\n"
        f"Guaranteed return: â‚¦{opp.guaranteed_return:,.0f} "
        f"(profit â‚¦{opp.guaranteed_return - (opp.stake_home + opp.stake_draw + opp.stake_away):,.0f})\n\n"
        f"âš ï¸ Odds move fast â€” verify all three prices on-site before staking. "
        f"This alert is based on data up to {max(opp.best_home.age_seconds(), opp.best_draw.age_seconds(), opp.best_away.age_seconds()):.0f}s old."
    )


def _post_sync(url: str, payload: dict) -> bool:
    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        return True
    except requests.RequestException as e:
        logger.error("Telegram request failed: %s", e)
        return False


async def send_alert(bot_token: str, chat_id: str, opp: ArbOpportunity) -> bool:
    text = format_alert(opp)
    url = TELEGRAM_API.format(token=bot_token)
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    return await asyncio.to_thread(_post_sync, url, payload)


async def send_status(bot_token: str, chat_id: str, text: str) -> bool:
    """For startup/error/heartbeat messages, not arb alerts."""
    url = TELEGRAM_API.format(token=bot_token)
    payload = {"chat_id": chat_id, "text": text}
    return await asyncio.to_thread(_post_sync, url, payload)
