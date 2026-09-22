"""
Common interface every bookmaker fetcher must implement.

Design goal: adding a new bookmaker (SportyBet, MSport, Betway, 1xBet â€” none of
which NaijaBet_Api covers) means writing ONE new class here that implements
`fetch_odds()`, nothing else in the system needs to change.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class OddsQuote:
    """A single 1X2 (home/draw/away) quote for one match, from one bookmaker."""
    bookmaker: str
    league: str
    home_team: str
    away_team: str
    kickoff_utc: datetime | None
    odds_home: float
    odds_draw: float
    odds_away: float
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def age_seconds(self) -> float:
        return (datetime.now(timezone.utc) - self.fetched_at).total_seconds()


class BookmakerFetcher(ABC):
    """Subclass this for each bookmaker."""

    name: str  # e.g. "bet9ja"

    @abstractmethod
    async def fetch_odds(self, league: str) -> list[OddsQuote]:
        """
        Return current 1X2 odds for all matches in the given league.
        Must raise on failure rather than silently returning stale/empty data â€”
        the caller needs to distinguish "no matches today" from "fetch broke".
        """
        raise NotImplementedError
