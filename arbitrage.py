"""
Core arbitrage calculation for 1X2 (home/draw/away) markets.

Math: implied probability of an outcome at decimal odds `o` is `1/o`. If you
take the BEST available odds for each of the three outcomes (possibly from
three different bookmakers) and the implied probabilities sum to LESS than 1,
you can stake proportionally across all three outcomes and profit regardless
of the result. This is real arbitrage math, not an approximation â€” but it
assumes:

  1. All three odds are simultaneously available and accurate (see the
     staleness filter below â€” this is the #1 way "arbs" turn out fake).
  2. You can actually get money on at each bookmaker before the odds move.
  3. You're not already stake-limited on the bookmaker giving the best price
     (a very common outcome once a bookmaker flags an account as an arber).

None of this module can verify (2) or (3) for you â€” it only guarantees the
math is sound given the input odds. Treat every alert as "worth checking
right now", not "guaranteed money".
"""

from dataclasses import dataclass

from fetchers.base import OddsQuote


@dataclass
class ArbOpportunity:
    league: str
    home_team: str
    away_team: str
    best_home: OddsQuote   # bookmaker + odds offering the best HOME price
    best_draw: OddsQuote
    best_away: OddsQuote
    implied_prob_sum: float
    profit_percent: float
    stake_home: float
    stake_draw: float
    stake_away: float
    guaranteed_return: float


def _best_quote_per_outcome(group: list[OddsQuote], max_age_seconds: float):
    """
    From quotes on the same fixture (possibly several per bookmaker over
    time â€” caller should pass one per bookmaker), drop stale ones and return
    the best price for each outcome. Returns None if fewer than 2 distinct
    bookmakers have fresh data (no cross-book arb possible with just one book).
    """
    fresh = [q for q in group if q.age_seconds() <= max_age_seconds]
    if len({q.bookmaker for q in fresh}) < 2:
        return None

    best_home = max(fresh, key=lambda q: q.odds_home)
    best_draw = max(fresh, key=lambda q: q.odds_draw)
    best_away = max(fresh, key=lambda q: q.odds_away)
    return best_home, best_draw, best_away


def evaluate_fixture(
    group: list[OddsQuote],
    max_age_seconds: float,
    min_profit_percent: float,
    reference_stake: float,
) -> ArbOpportunity | None:
    """
    Returns an ArbOpportunity if this fixture currently has a cross-bookmaker
    arb at or above min_profit_percent, else None.
    """
    best = _best_quote_per_outcome(group, max_age_seconds)
    if best is None:
        return None
    best_home, best_draw, best_away = best

    implied_sum = (
        1 / best_home.odds_home + 1 / best_draw.odds_draw + 1 / best_away.odds_away
    )
    if implied_sum >= 1.0:
        return None  # no arbitrage â€” bookmaker margins exceed the price gap

    profit_percent = (1 / implied_sum - 1) * 100
    if profit_percent < min_profit_percent:
        return None

    # Stake split that yields equal payout regardless of outcome
    total = reference_stake
    stake_home = total * (1 / best_home.odds_home) / implied_sum
    stake_draw = total * (1 / best_draw.odds_draw) / implied_sum
    stake_away = total * (1 / best_away.odds_away) / implied_sum
    guaranteed_return = stake_home * best_home.odds_home  # == stake_draw*odds_draw == stake_away*odds_away

    return ArbOpportunity(
        league=best_home.league,
        home_team=best_home.home_team,
        away_team=best_home.away_team,
        best_home=best_home,
        best_draw=best_draw,
        best_away=best_away,
        implied_prob_sum=implied_sum,
        profit_percent=profit_percent,
        stake_home=stake_home,
        stake_draw=stake_draw,
        stake_away=stake_away,
        guaranteed_return=guaranteed_return,
  )
