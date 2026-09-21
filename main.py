import os
import time
import logging
import requests
from datetime import datetime
from curl_cffi import requests as async_requests

# Configuration & Logging Setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)

# Environment Variables
ODDS_API_KEY = os.getenv("ODDS_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
PROXY_URL = os.getenv("PROXY_URL", "")  # e.g., http://vlzmxumu:d2m12x8awv7a@31.59.20.176:6754

# Approved Nigerian Bookmakers Mapping
APPROVED_NAIJA_BOOKIES = {
    "1xbet": "1xBet",
    "betway": "Betway",
    "betano": "Betano",
    "22bet": "22Bet",
    "melbet": "Melbet",
    "sportybet": "SportyBet",
    "bet9ja": "Bet9ja",
    "betking": "BetKing",
    "msport": "MSport"
}

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

def normalize_team_name(name: str) -> str:
    """Normalize team names for accurate arbitrage matching."""
    if not name:
        return ""
    clean = name.lower().strip()
    replacements = ["fc", "club", "utd", "united", "city", "town"]
    for word in replacements:
        clean = clean.replace(f" {word}", "").replace(f"{word} ", "")
    return "".join(e for e in clean if e.isalnum())

def format_match_date(date_str: str) -> str:
    """Format match timestamps into readable string."""
    try:
        if isinstance(date_str, (int, float)):
            dt = datetime.fromtimestamp(date_str / 1000)
        else:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "Upcoming"

# --- SCRAPERS ---

def fetch_odds_api_markets() -> list:
    """Fetch odds from The Odds API for Nigerian bookmakers."""
    if not ODDS_API_KEY:
        logging.warning("[Odds API] No API key provided.")
        return []

    url = f"https://api.the-odds-api.com/v4/sports/soccer/odds/"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": "eu,uk",
        "markets": "h2h",
        "dateFormat": "iso"
    }

    odds_entries = []
    try:
        response = requests.get(url, params=params, timeout=15)
        if response.status_code == 200:
            events = response.json()
            for ev in events:
                home, away = ev.get("home_team"), ev.get("away_team")
                match_time = format_match_date(ev.get("commence_time"))
                
                for bkm in ev.get("bookmakers", []):
                    bkm_key = bkm.get("key", "").lower()
                    if bkm_key in APPROVED_NAIJA_BOOKIES:
                        for mkt in bkm.get("markets", []):
                            if mkt.get("key") == "h2h":
                                odds = {}
                                for out in mkt.get("outcomes", []):
                                    if out.get("name") == home:
                                        odds["Home"] = float(out.get("price", 0))
                                    elif out.get("name") == away:
                                        odds["Away"] = float(out.get("price", 0))
                                    elif out.get("name") == "Draw":
                                        odds["Draw"] = float(out.get("price", 0))
                                
                                if len(odds) == 3:
                                    odds_entries.append({
                                        "bookie": APPROVED_NAIJA_BOOKIES[bkm_key],
                                        "home": home,
                                        "away": away,
                                        "match_date": match_time,
                                        "norm_key": f"{normalize_team_name(home)}_{normalize_team_name(away)}",
                                        "odds": odds
                                    })
        logging.info(f"[Odds API] Fetched {len(odds_entries)} valid Nigerian bookmaker odds entries.")
    except Exception as e:
        logging.error(f"[Odds API Error]: {e}")

    return odds_entries

def fetch_sportybet_direct() -> list:
    """Fetch SportyBet odds bypassing Cloudflare via curl_cffi and Proxy."""
    url = "https://www.sportybet.com/api/ng/factsCenter/upcomingEvents"
    params = {"sportId": "sr:sport:1", "marketId": "1", "pageSize": 50}
    matches = []
    
    proxies = {"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None

    try:
        res = async_requests.get(
            url, 
            params=params, 
            headers=DEFAULT_HEADERS, 
            impersonate="chrome120", 
            proxies=proxies, 
            timeout=12
        )
        if res.status_code == 200:
            data = res.json()
            for tourney in data.get("data", {}).get("tournaments", []):
                for ev in tourney.get("events", []):
                    home, away = ev.get("homeTeamName"), ev.get("awayTeamName")
                    match_time = format_match_date(ev.get("estimateStartTime"))
                    if not home or not away:
                        continue
                    
                    odds = {}
                    for mkt in ev.get("markets", []):
                        if mkt.get("id") == "1":
                            for out in mkt.get("outcomes", []):
                                if out.get("desc") == "1": odds["Home"] = float(out.get("odds", 0))
                                elif out.get("desc") == "X": odds["Draw"] = float(out.get("odds", 0))
                                elif out.get("desc") == "2": odds["Away"] = float(out.get("odds", 0))
                    
                    if len(odds) == 3:
                        matches.append({
                            "bookie": APPROVED_NAIJA_BOOKIES["sportybet"],
                            "home": home,
                            "away": away,
                            "match_date": match_time,
                            "norm_key": f"{normalize_team_name(home)}_{normalize_team_name(away)}",
                            "odds": odds
                        })
        logging.info(f"[SportyBet] Fetched {len(matches)} matches.")
    except Exception as e:
        logging.warning(f"[SportyBet Error]: {e}")
        
    return matches

# --- ARBITRAGE CALCULATOR ---

def calculate_arbitrage(all_matches: list) -> list:
    """Group matches by normalized team key and check for SureBet profit margins."""
    grouped = {}
    for entry in all_matches:
        key = entry["norm_key"]
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(entry)

    surebets = []
    for key, entries in grouped.items():
        if len(entries) < 2:
            continue

        best_home = max(entries, key=lambda x: x["odds"]["Home"])
        best_draw = max(entries, key=lambda x: x["odds"]["Draw"])
        best_away = max(entries, key=lambda x: x["odds"]["Away"])

        o1, o2, o3 = best_home["odds"]["Home"], best_draw["odds"]["Draw"], best_away["odds"]["Away"]
        if o1 <= 0 or o2 <= 0 or o3 <= 0:
            continue

        arb_margin = (1 / o1) + (1 / o2) + (1 / o3)
        if arb_margin < 1.0:
            profit_pct = round((1 - arb_margin) * 100, 2)
            surebets.append({
                "match": f"{best_home['home']} vs {best_home['away']}",
                "match_date": best_home["match_date"],
                "profit": profit_pct,
                "outcomes": {
                    "Home": {"bookie": best_home["bookie"], "odds": o1},
                    "Draw": {"bookie": best_draw["bookie"], "odds": o2},
                    "Away": {"bookie": best_away["bookie"], "odds": o3}
                }
            })
    return surebets

def send_telegram_alert(surebets: list):
    """Send alert to Telegram channel when arbitrage is found."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    for sb in surebets:
        msg = (
            f"🚨 <b>SUREBET OPPORTUNITY ({sb['profit']}%)</b> 🚨\n\n"
            f"⚽ <b>Match:</b> {sb['match']}\n"
            f"📅 <b>Date:</b> {sb['match_date']}\n\n"
            f"🔹 <b>Home (1):</b> {sb['outcomes']['Home']['odds']} @ {sb['outcomes']['Home']['bookie']}\n"
            f"🔹 <b>Draw (X):</b> {sb['outcomes']['Draw']['odds']} @ {sb['outcomes']['Draw']['bookie']}\n"
            f"🔹 <b>Away (2):</b> {sb['outcomes']['Away']['odds']} @ {sb['outcomes']['Away']['bookie']}\n"
        )
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"}
        try:
            requests.post(url, json=payload, timeout=5)
        except Exception as e:
            logging.error(f"[Telegram Error]: {e}")

# --- MAIN EXECUTION ENGINE ---

def run_scan():
    """Main scanning routine."""
    logging.info("--- Starting Arbitrage Engine Scan ---")
    
    odds_api_results = fetch_odds_api_markets()
    sportybet_results = fetch_sportybet_direct()
    
    all_data = odds_api_results + sportybet_results
    
    surebets = calculate_arbitrage(all_data)
    logging.info(f"Scan complete: Found {len(surebets)} valid arbitrage opportunities.")
    
    if surebets:
        send_telegram_alert(surebets)

if __name__ == "__main__":
    logging.info("Naija Arb Engine Online (Strictly Nigerian Bookies Mode)")
    while True:
        run_scan()
        time.sleep(300)  # Runs every 5 minutes
