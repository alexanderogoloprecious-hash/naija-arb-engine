"""
Fetchers for Bet9ja and NairaBet, backed by the open-source NaijaBet_Api library.

    pip install NaijaBet-Api

NaijaBet_Api is a synchronous library, so we run its calls in a thread pool to
keep the rest of the system async. This is real scraped data from the
bookmakers' own endpoints â€” not simulated â€” but it inherits that library's
maintenance state: if Bet9ja/NairaBet change their site, this breaks until the
library (or your fork of it) is updated. Treat fetch exceptions as "data
unavailable", never as "zero matches" or "odds of 0".
"""

import asyncio
import logging
from datetime import datetime, timezone

from .base import BookmakerFetcher, OddsQuote

logger = logging.getLogger(__name__)

try:
    from NaijaBet_Api.bookmakers import Bet9ja, Nairabet
    from NaijaBet_Api.id import Betid
except ImportError:  # pragma: no cover
    Bet9ja = Nairabet = Betid = None
    logger.warning("NaijaBet_Api not installed â€” run: pip install NaijaBet-Api")


_LEAGUE_MAP = {
    "PREMIERLEAGUE": "PREMIERLEAGUE",
    "LALIGA": "LALIGA",
    "SERIEA": "SERIEA",
    "BUNDESLIGA": "BUNDESLIGA",
    "UEFA_CHAMPIONS_LEAGUE": "UEFA_CHAMPIONS_LEAGUE",
}


def _parse_rows(raw_rows: list[dict], bookmaker: str, league: str) -> list[OddsQuote]:
    """
    Normalize NaijaBet_Api's raw dict output into OddsQuote objects.

    Verified real shape (from the library's own published example output):

        {'home': 4.0, 'draw': 3.75, 'away': 1.92,
         'match': 'Brentford FC - Arsenal FC', 'league': 'Premier League',
         'league_id': 135975, 'match_id': 4467373, 'time': 1628881200000}

    Two things this fixes vs. the first version: the odds keys are plain
    'home'/'draw'/'away' (not 'odds_home' etc.), and there's no separate
    home/away team field â€” it's a single 'match' string of the form
    "Home Team - Away Team" that has to be split. 'time' is milliseconds
    since epoch. This is what's actually documented; it's still worth a
    one-off print of real output on your installed version before trusting
    it blindly, since a library at 0.2.x can still change shape.
    """
    quotes = []
    for row in raw_rows:
        try:
            match_str = row.get("match", "")
            if " - " not in match_str:
                logger.debug("Skipping row with unparsable match string: %r", match_str)
                continue
            home, away = (part.strip() for part in match_str.split(" - ", 1))

            odds_home = float(row["home"])
            odds_draw = float(row["draw"])
            odds_away = float(row["away"])

            kickoff = None
            if row.get("time"):
                kickoff = datetime.fromtimestamp(row["time"] / 1000, tz=timezone.utc)

            quotes.append(OddsQuote(
                bookmaker=bookmaker,
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
            logger.debug("Skipping malformed row from %s: %s (%s)", bookmaker, row, e)
            continue
    return quotes


class Bet9jaFetcher(BookmakerFetcher):
    name = "bet9ja"

    def __init__(self):
        if Bet9ja is None:
            raise RuntimeError("NaijaBet_Api not installed")
        self._client = Bet9ja()

    async def fetch_odds(self, league: str) -> list[OddsQuote]:
        league_id = getattr(Betid, _LEAGUE_MAP.get(league, ""), None)
        if league_id is None:
            raise ValueError(f"Unknown or unsupported league: {league}")
        loop = asyncio.get_running_loop()
        raw = await loop.run_in_executor(None, self._client.get_league, league_id)
        return _parse_rows(raw, self.name, league)


class NairabetFetcher(BookmakerFetcher):
    name = "nairabet"

    def __init__(self):
        if Nairabet is None:
            raise RuntimeError("NaijaBet_Api not installed")
        self._client = Nairabet()

    async def fetch_odds(self, league: str) -> list[OddsQuote]:
        league_id = getattr(Betid, _LEAGUE_MAP.get(league, ""), None)
        if league_id is None:
            raise ValueError(f"Unknown or unsupported league: {league}")
        loop = asyncio.get_running_loop()
        raw = await loop.run_in_executor(None, self._client.get_league, league_id)
        return _parse_rows(raw, self.name, league)
