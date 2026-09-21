import os
import re
import time
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.server import HTTPServer, BaseHTTPRequestHandler

# Import curl_cffi for Cloudflare TLS-fingerprint bypass
try:
    from curl_cffi import requests as cf_requests
except ImportError:
    import requests as cf_requests

import requests  # Standard requests fallback

# ---------------------------------------------------------------------------
# Logging Setup
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# ---------------------------------------------------------------------------
# Environment Variables
# ---------------------------------------------------------------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
ODDS_API_KEY = os.getenv("ODDS_API_KEY", "")        # Optional: Odds API Key
PROXY_URL = os.getenv("PROXY_URL", "")              # Optional: Proxy URL (e.g., http://user:pass@ip:port)
SCAN_INTERVAL_SECONDS = int(os.getenv("SCAN_INTERVAL_SECONDS", 45))
PORT = int(os.getenv("PORT", 10000))
TOTAL_STAKE = float(os.getenv("TOTAL_STAKE", 10000.0))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

# Configured Proxy Dictionary
PROXIES = {"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None

# ---------------------------------------------------------------------------
# Keep-Alive Health Server (Render & UptimeRobot Compliant)
# ---------------------------------------------------------------------------
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Naija Multi-Bookie Arb Engine Active!")

    def log_message(self, format, *args):
        return

def start_health_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthCheckHandler)
    logging.info(f"Health check server running on port {PORT}")
    server.serve_forever()

# ---------------------------------------------------------------------------
# Telegram Notifications
# ---------------------------------------------------------------------------
def send_telegram_alert(message: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logging.error("Telegram credentials missing.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    try:
        res = requests.post(url, json=payload, timeout=10)
        res.raise_for_status()
        return True
    except Exception as e:
        logging.error(f"Failed to deliver Telegram alert: {e}")
        return False

# ---------------------------------------------------------------------------
# Helper Functions & Normalization
# ---------------------------------------------------------------------------
def normalize_team(name: str) -> str:
    name = name.lower()
    for word in [" fc", "fc ", " cf", "cf ", " united", " utd", " town", " city", " athletic"]:
        name = name.replace(word, "")
    return re.sub(r'[^a-z0-9]', '', name)

def safe_get(url, params=None):
    """Executes requests using curl_cffi Chrome impersonation with proxy fallback."""
    try:
        res = cf_requests.get(
            url,
            params=params,
            headers=HEADERS,
            impersonate="chrome",  # Set to generic chrome for universal version compatibility
            proxies=PROXIES,
            timeout=10
        )
        if res.status_code == 200:
            return res.json()
    except Exception as e:
        logging.warning(f"Failed fetch for {url}: {e}")
    return None

# ---------------------------------------------------------------------------
# Direct Bookmaker Scrapers (Options 1 & 2)
# ---------------------------------------------------------------------------
def fetch_sportybet():
    url = "https://www.sportybet.com/api/ng/factsCenter/upcomingEvents"
    data = safe_get(url, params={"sportId": "sr:sport:1", "pageSize": 50})
    matches = []
    if data:
        for tourney in data.get("data", {}).get("tournaments", []):
            for ev in tourney.get("events", []):
                home, away = ev.get("homeTeamName"), ev.get("awayTeamName")
                if not home or not away: continue
                odds = {}
                for mkt in ev.get("markets", []):
                    if mkt.get("id") == "1":
                        for out in mkt.get("outcomes", []):
                            if out.get("desc") == "1": odds["1"] = float(out.get("odds", 0))
                            elif out.get("desc") == "X": odds["X"] = float(out.get("odds", 0))
                            elif out.get("desc") == "2": odds["2"] = float(out.get("odds", 0))
                if len(odds) == 3:
                    matches.append({
                        "bookie": "SportyBet", "home": home, "away": away,
                        "key": f"{normalize_team(home)}_{normalize_team(away)}", "odds": odds
                    })
    logging.info(f"[SportyBet] Fetched {len(matches)} matches")
    return matches

def fetch_bet9ja():
    url = "https://sports.bet9ja.com/desktop/feapi/Palimpsest/GetPrematchEvents"
    data = safe_get(url, params={"SPORT_ID": 1, "LIMIT": 50})
    matches = []
    if data:
        for ev in data.get("D", {}).get("E", []):
            home, away = ev.get("H"), ev.get("A")
            if not home or not away: continue
            raw_odds = ev.get("O", {})
            h, d, a = raw_odds.get("1"), raw_odds.get("X"), raw_odds.get("2")
            if h and d and a:
                matches.append({
                    "bookie": "Bet9ja", "home": home, "away": away,
                    "key": f"{normalize_team(home)}_{normalize_team(away)}",
                    "odds": {"1": float(h), "X": float(d), "2": float(a)}
                })
    logging.info(f"[Bet9ja] Fetched {len(matches)} matches")
    return matches

def fetch_msport():
    url = "https://www.msport.com/api/ng/factsCenter/upcomingEvents"
    data = safe_get(url, params={"sportId": "sr:sport:1", "pageSize": 50})
    matches = []
    if data:
        for tourney in data.get("data", {}).get("tournaments", []):
            for ev in tourney.get("events", []):
                home, away = ev.get("homeTeamName"), ev.get("awayTeamName")
                if not home or not away: continue
                odds = {}
                for mkt in ev.get("markets", []):
                    if mkt.get("id") == "1":
                        for out in mkt.get("outcomes", []):
                            if out.get("desc") == "1": odds["1"] = float(out.get("odds", 0))
                            elif out.get("desc") == "X": odds["X"] = float(out.get("odds", 0))
                            elif out.get("desc") == "2": odds["2"] = float(out.get("odds", 0))
                if len(odds) == 3:
                    matches.append({
                        "bookie": "MSport", "home": home, "away": away,
                        "key": f"{normalize_team(home)}_{normalize_team(away)}", "odds": odds
                    })
    logging.info(f"[MSport] Fetched {len(matches)} matches")
    return matches

# ---------------------------------------------------------------------------
# The Odds API Scraper (Option 3 Backup)
# ---------------------------------------------------------------------------
def fetch_odds_api():
    if not ODDS_API_KEY:
        return []
    url = "https://api.the-odds-api.com/v4/sports/soccer/odds"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": "eu,uk",
        "markets": "h2h"
    }
    matches = []
    try:
        res = requests.get(url, params=params, timeout=10)
        if res.status_code == 200:
            for game in res.json():
                home, away = game.get("home_team"), game.get("away_team")
                for bookie in game.get("bookmakers", []):
                    b_title = bookie.get("title")
                    for mkt in bookie.get("markets", []):
                        if mkt.get("key") == "h2h":
                            odds = {}
                            for outcome in mkt.get("outcomes", []):
                                if outcome.get("name") == home: odds["1"] = float(outcome.get("price"))
                                elif outcome.get("name") == away: odds["2"] = float(outcome.get("price"))
                                elif outcome.get("name") == "Draw": odds["X"] = float(outcome.get("price"))
                            if len(odds) == 3:
                                matches.append({
                                    "bookie": f"{b_title} (OddsAPI)", "home": home, "away": away,
                                    "key": f"{normalize_team(home)}_{normalize_team(away)}", "odds": odds
                                })
    except Exception as e:
        logging.warning(f"[OddsAPI Error]: {e}")
    logging.info(f"[Odds API] Fetched {len(matches)} matches")
    return matches

# ---------------------------------------------------------------------------
# Master Execution & Aggregation Engine
# ---------------------------------------------------------------------------
def run_all_scrapers():
    scrapers = [fetch_sportybet, fetch_bet9ja, fetch_msport, fetch_odds_api]
    all_matches = []

    with ThreadPoolExecutor(max_workers=len(scrapers)) as executor:
        futures = [executor.submit(s) for s in scrapers]
        for future in as_completed(futures):
            all_matches.extend(future.result())

    aggregated = {}
    for match in all_matches:
        key = match["key"]
        if key not in aggregated:
            aggregated[key] = {
                "display": f"{match['home']} vs {match['away']}",
                "outcomes": {"1": [], "X": [], "2": []}
            }
        for o_type, val in match["odds"].items():
            if val > 1.0:
                aggregated[key]["outcomes"][o_type].append({"bookie": match["bookie"], "odds": val})

    arbs_count = 0
    for key, data in aggregated.items():
        outs = data["outcomes"]
        if outs["1"] and outs["X"] and outs["2"]:
            best_1 = max(outs["1"], key=lambda x: x["odds"])
            best_X = max(outs["X"], key=lambda x: x["odds"])
            best_2 = max(outs["2"], key=lambda x: x["odds"])

            implied_sum = (1.0 / best_1["odds"]) + (1.0 / best_X["odds"]) + (1.0 / best_2["odds"])

            if implied_sum < 1.0:
                roi = round(((1.0 / implied_sum) - 1.0) * 100, 2)
                if 0.5 <= roi <= 20.0:
                    arbs_count += 1
                    s1 = round((TOTAL_STAKE / best_1["odds"]) / implied_sum, 2)
                    sx = round((TOTAL_STAKE / best_X["odds"]) / implied_sum, 2)
                    s2 = round((TOTAL_STAKE / best_2["odds"]) / implied_sum, 2)
                    profit = round((TOTAL_STAKE / implied_sum) - TOTAL_STAKE, 2)

                    msg = (
                        f"⚡ *HYBRID SUREBET FOUND* ⚡\n\n"
                        f"⚽ *Match*: {data['display']}\n"
                        f"📈 *ROI*: *+{roi}%* | *Profit*: *₦{profit:,.2f}*\n\n"
                        f"📌 *STAKE BREAKDOWN (Total ₦{TOTAL_STAKE:,.0f})*:\n"
                        f"• *1 (Home)*: {best_1['bookie']} @ *{best_1['odds']}* ➔ Bet *₦{s1:,.2f}*\n"
                        f"• *X (Draw)*: {best_X['bookie']} @ *{best_X['odds']}* ➔ Bet *₦{sx:,.2f}*\n"
                        f"• *2 (Away)*: {best_2['bookie']} @ *{best_2['odds']}* ➔ Bet *₦{s2:,.2f}*\n"
                    )
                    send_telegram_alert(msg)

    logging.info(f"Scan finished: {arbs_count} surebets detected.")

# ---------------------------------------------------------------------------
# Script Initialization
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    threading.Thread(target=start_health_server, daemon=True).start()
    logging.info("Multi-Strategy Arb Engine Online")
    send_telegram_alert("🚀 *Multi-Strategy Engine Active!* Using Browser Impersonation + Proxies + Odds API...")

    while True:
        try:
            run_all_scrapers()
        except Exception as e:
            logging.error(f"Main loop error: {e}")
        time.sleep(SCAN_INTERVAL_SECONDS)
