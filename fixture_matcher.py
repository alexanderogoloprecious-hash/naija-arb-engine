"""
Groups OddsQuotes from different bookmakers that represent the SAME real
match, so the arbitrage engine compares odds for the same event rather than
accidentally pairing "Man Utd vs Chelsea" on one book with "Man City vs
Chelsea" on another.

Bookmakers spell team names differently ("Man Utd" vs "Manchester United" vs
"Manchester Utd"), so this uses fuzzy string matching rather than exact
equality. This is a real accuracy risk in the system: a false match produces
a fake arbitrage alert. difflib is a reasonable v1; if false matches show up
in practice, upgrade to a proper team-name alias table (built from what you
observe each bookmaker calling each club) rather than tuning the threshold
blindly.
"""

from difflib import SequenceMatcher

from fetchers.base import OddsQuote


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def _same_fixture(q1: OddsQuote, q2: OddsQuote, threshold: float) -> bool:
    if q1.league != q2.league:
        return False
    home_sim = _similarity(q1.home_team, q2.home_team)
    away_sim = _similarity(q1.away_team, q2.away_team)
    return home_sim >= threshold and away_sim >= threshold


def group_by_fixture(
    quotes: list[OddsQuote], threshold: float
) -> list[list[OddsQuote]]:
    """
    Cluster quotes into groups that represent the same match. Returns a list
    of groups; each group has at most one quote per bookmaker (if a
    bookmaker appears twice for what looks like the same fixture, only the
    freshest quote is kept â€” that shouldn't normally happen within one poll
    cycle, but guards against duplicate fetch results).
    """
    groups: list[list[OddsQuote]] = []

    for quote in quotes:
        placed = False
        for group in groups:
            if _same_fixture(group[0], quote, threshold):
                existing = next((q for q in group if q.bookmaker == quote.bookmaker), None)
                if existing is None:
                    group.append(quote)
                elif quote.fetched_at > existing.fetched_at:
                    group.remove(existing)
                    group.append(quote)
                placed = True
                break
        if not placed:
            groups.append([quote])

    return groups
