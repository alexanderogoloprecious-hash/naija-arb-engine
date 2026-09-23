"""
Bet9ja fetcher using curl_cffi against Bet9ja's own internal mobile API,
reverse-engineered directly from browser DevTools rather than relying on
NaijaBet_Api's Bet9ja scraper (which is currently blocked with HTTP 403).

Verified real endpoint and response shape (captured live, Sep 2026):

    GET https://sports.bet9ja.com/mobile/feapi/PalimpsestAjax/GetEventsInGroupV2
        ?GROUPID=<league group id>&DISP=0&GROUPMARKETID=1&v_cache_version=<version>

    {"R":"OK","D":{"GID":..., "GN":"Premier League", "SG":"England",
     "E":[{"DS":"Arsenal - Leeds Utd", "O":{"S_1X2_1":"1.38",
           "S_1X2_X":"5.05","S_1X2_2":"7.8", ...}}, ...]}}

IMPORTANT: GROUPID in the URL is NOT reliably the same as the "GID" field
inside the response, and GROUPIDs can be reassigned to a different league
over time -- treat them as opaque values captured from real browser
traffic, never guessed or assumed permanent.
"""

import asyncio
import logging
from datetime import datetime, timezone

from curl_cffi import requests as cffi_requests

from .base import BookmakerFetcher, OddsQuote

logger = logging.getLogger(__name__)

BASE_URL = "https://sports.bet9ja.com/mobile/feapi/PalimpsestAjax/GetEventsInGroupV2"

# GROUPID per league, captured directly from bet9ja.com via DevTools.
LEAGUE_GROUP_IDS = {
    "PREMIERLEAGUE": 170880,
    "LALIGA": 180928,
    "SERIEA": 167856,
    "BUNDESLIGA": 180923,
    "LIGUE1": 950503,
}

# Sent alongside requests on Bet9ja's own site. If Bet9ja updates their app
# this may need refreshing from a new DevTools capture.
CACHE_VERSION = "1.326.2.248"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
    ),
    "Referer": "https://sports.bet9ja.com/",
    "Accept": "application/json, text/plain, */*",
}


class Bet9jaCffiFetcher(BookmakerFetcher):
    name = "bet9ja"

    async def fetch_odds(self, league: str) -> list[OddsQuote]:
        group_id = LEAGUE_GROUP_IDS.get(league)
        if group_id is None:
            raise ValueError(
                f"No captured GROUPID for league '{league}' yet -- "
                f"see README for how to capture one from bet9ja.com"
            )

        loop = asyncio.get_running_loop()
        data = await loop.run_in_executor(None, self._fetch_sync, group_id)

        if data.get("R") != "OK":
            raise RuntimeError(f"Bet9ja returned non-OK response: {data.get('R')}")

        events = data.get("D", {}).get("E", [])
        quotes = []
        for event in events:
            try:
                match_str = event.get("DS", "")
                if " - " not in match_str:
                    continue
                home, away = (p.strip() for p in match_str.split(" - ", 1))

                odds = event.get("O", {})
                odds_home = float(odds["S_1X2_1"])
                odds_draw = float(odds["S_1X2_X"])
                odds_away = float(odds["S_1X2_2"])

                kickoff = None
                raw_dt = event.get("STARTDATEUTC")
                if raw_dt:
                    kickoff = datetime.fromisoformat(raw_dt.replace("Z", "+00:00"))

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
            except (KeyError, ValueError, TypeError) as e:
                logger.debug("Skipping malformed Bet9ja event: %s (%s)", event, e)
                continue
        return quotes

    def _fetch_sync(self, group_id: int) -> dict:
        params = {
            "GROUPID": group_id,
            "DISP": 0,
            "GROUPMARKETID": 1,
            "v_cache_version": CACHE_VERSION,
        }
        resp = cffi_requests.get(
            BASE_URL, params=params, headers=HEADERS,
            impersonate="chrome124", timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
