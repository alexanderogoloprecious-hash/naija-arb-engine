"""
BetKing fetcher â€” BetKing is behind Cloudflare, so NaijaBet_Api's Betking
integration drives a real headless browser (Playwright) rather than hitting
an endpoint directly. This is slower and heavier than the Bet9ja/NairaBet
fetchers (seconds per call, not milliseconds) â€” budget your poll interval
accordingly, or poll BetKing less frequently than the others.

    pip install playwright
    playwright install chromium
"""

import asyncio
import logging
from datetime import datetime, timezone

from .base import BookmakerFetcher, OddsQuote

logger = logging.getLogger(__name__)

try:
    from NaijaBet_Api.bookmakers import BetkingPlaywright
    from NaijaBet_Api.id import Betid
except ImportError:  # pragma: no cover
    BetkingPlaywright = Betid = None
    logger.warning("NaijaBet_Api / Playwright not installed for BetKing fetcher")

_LEAGUE_MAP = {
    "PREMIERLEAGUE": "PREMIERLEAGUE",
    "LALIGA": "LALIGA",
    "SERIEA": "SERIEA",
    "BUNDESLIGA": "BUNDESLIGA",
    "UEFA_CHAMPIONS_LEAGUE": "UEFA_CHAMPIONS_LEAGUE",
}


class BetkingFetcher(BookmakerFetcher):
    name = "betking"

    def _fetch_sync(self, league_id) -> list[dict]:
        # Context manager per call keeps this safe to run from a thread pool
        # repeatedly without leaking browser instances.
        with BetkingPlaywright() as betking:
            return betking.get_league(league_id)

    async def fetch_odds(self, league: str) -> list[OddsQuote]:
        if BetkingPlaywright is None:
            raise RuntimeError("Playwright / NaijaBet_Api BetKing support not installed")
        league_id = getattr(Betid, _LEAGUE_MAP.get(league, ""), None)
        if league_id is None:
            raise ValueError(f"Unknown or unsupported league: {league}")

        loop = asyncio.get_running_loop()
        raw = await loop.run_in_executor(None, self._fetch_sync, league_id)

        # Same NaijaBet_Api output shape as Bet9ja/NairaBet: plain
        # 'home'/'draw'/'away' odds keys and a single 'match' string like
        # "Home Team - Away Team" rather than separate team fields.
        quotes = []
        for row in raw:
            try:
                match_str = row.get("match", "")
                if " - " not in match_str:
                    logger.debug("Skipping BetKing row with unparsable match: %r", match_str)
                    continue
                home, away = (part.strip() for part in match_str.split(" - ", 1))

                odds_home = float(row["home"])
                odds_draw = float(row["draw"])
                odds_away = float(row["away"])

                kickoff = None
                if row.get("time"):
                    kickoff = datetime.fromtimestamp(row["time"] / 1000, tz=timezone.utc)

                quotes.append(OddsQuote(
                    bookmaker=self.name,
                    league=league,
                    home_team=home,
                    away_team=away,
                    kickoff_utc=kickoff,
                    odds_home=odds_home,
                    odds_draw=odds_draw,
                    odds_away=odds_away,
                    fetched_at=datetime.now(timezone.utc),
                ))
            except (TypeError, ValueError, KeyError) as e:
                logger.debug("Skipping malformed BetKing row: %s (%s)", row, e)
                continue
        return quotes
