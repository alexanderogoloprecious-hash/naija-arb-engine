import os
import re
import time
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests
from google import genai

# ---------------------------------------------------------------------------
# Global Settings
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GEMINI_API_KEYS_RAW = os.getenv("GEMINI_API_KEY", "")
ODDS_API_KEY = os.getenv("ODDS_API_KEY")
PORT = int(os.getenv("PORT", 10000))
SCAN_INTERVAL_SECONDS = int(os.getenv("SCAN_INTERVAL_SECONDS", 300))
DEFAULT_BANKROLL = float(os.getenv("DEFAULT_BANKROLL", 100000))  # ₦100,000

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 13; Mobile) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

# ---------------------------------------------------------------------------
# Health Server (Render Keep-Alive)
# ---------------------------------------------------------------------------
class HealthServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Naija Multi-Bookie Arb Engine is ONLINE.")

    def log_message(self, format, *args):
        return

def start_health_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthServer)
    server.serve_forever()

# ---------------------------------------------------------------------------
# Fuzzy Team Name Matching & Normalization
# ---------------------------------------------------------------------------
def normalize_team_name(name: str) -> str:
    """Normalizes variations like 'Chelsea FC', 'Chelsea', and 'Chelsea City'."""
    name = name.lower()
    for word in [" fc", "fc ", " cf", "cf ", " united", " utd", " town", " city", " athletic", " ath"]:
        name = name.replace(word, "")
    return re.sub(r'[^a-z0-9]', '', name)

# ---------------------------------------------------------------------------
# Bookmaker Scrapers
# ---------------------------------------------------------------------------
def fetch_sportybet():
    """SportyBet Nigeria Direct Scraper"""
    url = "https://www.sportybet.com/api/ng/factsCenter/upcomingEvents"
    params = {"sportId": "sr:sport:1", "marketId": "1", "pageSize": 50}
    headers = {**DEFAULT_HEADERS, "Referer": "https://www.sportybet.com/ng/"}
    matches = []
    try:
        res = requests.get(url, params=params, headers=headers, timeout=8)
        if res.status_code == 200:
            for tourney in res.json().get("data", {}).get("tournaments", []):
                for ev in tourney.get("events", []):
                    home, away = ev.get("homeTeamName"), ev.get("awayTeamName")
                    if not home or not away: continue
                    odds = {}
                    for mkt in ev.get("markets", []):
                        if mkt.get("id") == "1":
                            for out in mkt.get("outcomes", []):
                                if out.get("desc") == "1": odds["Home"] = float(out.get("odds", 0))
                                elif out.get("desc") == "X": odds["Draw"] = float(out.get("odds", 0))
                                elif out.get("desc") == "2": odds["Away"] = float(out.get("odds", 0))
                    if len(odds) == 3:
                        matches.append({
                            "bookie": "SportyBet", "home": home, "away": away,
                            "norm_key": f"{normalize_team_name(home)}_{normalize_team_name(away)}", "odds": odds
                        })
    except Exception as e:
        logging.warning(f"[SportyBet Scraper Warning]: {e}")
    return matches

def fetch_bet9ja():
    """Bet9ja Nigeria Direct Scraper"""
    url = "https://sports.bet9ja.com/desktop/feapi/Palimpsest/GetPrematchEvents"
    params = {"sportId": 1, "dayOffset": 0, "pageSize": 50}
    headers = {**DEFAULT_HEADERS, "Referer": "https://sports.bet9ja.com/"}
    matches = []
    try:
        res = requests.get(url, params=params, headers=headers, timeout=8)
        if res.status_code == 200:
            for ev in res.json().get("data", {}).get("events", []):
                home, away = ev.get("home_team"), ev.get("away_team")
                if not home or not away: continue
                raw_odds = ev.get("odds", {})
                odds = {
                    "Home": float(raw_odds.get("1", 0)),
                    "Draw": float(raw_odds.get("X", 0)),
                    "Away": float(raw_odds.get("2", 0))
                }
                if all(v > 1.0 for v in odds.values()):
                    matches.append({
                        "bookie": "Bet9ja", "home": home, "away": away,
                        "norm_key": f"{normalize_team_name(home)}_{normalize_team_name(away)}", "odds": odds
                    })
    except Exception as e:
        logging.warning(f"[Bet9ja Scraper Warning]: {e}")
    return matches

def fetch_betking():
    """BetKing Nigeria Direct Scraper"""
    url = "https://m.betking.com/api/sports/events/prematch"
    params = {"sportId": 1, "pageSize": 50}
    headers = {**DEFAULT_HEADERS, "Referer": "https://m.betking.com/"}
    matches = []
    try:
        res = requests.get(url, params=params, headers=headers, timeout=8)
        if res.status_code == 200:
            for ev in res.json().get("data", []):
                home, away = ev.get("homeTeam"), ev.get("awayTeam")
                if not home or not away: continue
                odds = {}
                for mkt in ev.get("markets", []):
                    if mkt.get("name") in ["1X2", "Match Result"]:
                        for opt in mkt.get("options", []):
                            if opt.get("name") in ["1", "Home"]: odds["Home"] = float(opt.get("odds", 0))
                            elif opt.get("name") in ["X", "Draw"]: odds["Draw"] = float(opt.get("odds", 0))
                            elif opt.get("name") in ["2", "Away"]: odds["Away"] = float(opt.get("odds", 0))
                if len(odds) == 3:
                    matches.append({
                        "bookie": "BetKing", "home": home, "away": away,
                        "norm_key": f"{normalize_team_name(home)}_{normalize_team_name(away)}", "odds": odds
                    })
    except Exception as e:
        logging.warning(f"[BetKing Scraper Warning]: {e}")
    return matches

def fetch_1xbet():
    """1xBet / 22Bet / Melbet API Scraper"""
    url = "https://1xbet.ng/LineFeed/Get1x2Zip"
    params = {"sports": 1, "count": 50, "lng": "en"}
    headers = {**DEFAULT_HEADERS, "Referer": "https://1xbet.ng/"}
    matches = []
    try:
        res = requests.get(url, params=params, headers=headers, timeout=8)
        if res.status_code == 200:
            for ev in res.json().get("Value", []):
                home, away = ev.get("O1"), ev.get("O2")
                if not home or not away: continue
                odds = {}
                for elem in ev.get("E", []):
                    if elem.get("T") == 1: odds["Home"] = float(elem.get("C", 0))
                    elif elem.get("T") == 2: odds["Draw"] = float(elem.get("C", 0))
                    elif elem.get("T") == 3: odds["Away"] = float(elem.get("C", 0))
                if len(odds) == 3:
                    matches.append({
                        "bookie": "1xBet", "home": home, "away": away,
                        "norm_key": f"{normalize_team_name(home)}_{normalize_team_name(away)}", "odds": odds
                    })
    except Exception as e:
        logging.warning(f"[1xBet Scraper Warning]: {e}")
    return matches

def fetch_msport():
    """MSport Nigeria Direct Scraper"""
    url = "https://www.msport.com/api/ng/factsCenter/upcomingEvents"
    params = {"sportId": "sr:sport:1", "marketId": "1", "pageSize": 50}
    headers = {**DEFAULT_HEADERS, "Referer": "https://www.msport.com/ng/"}
    matches = []
    try:
        res = requests.get(url, params=params, headers=headers, timeout=8)
        if res.status_code == 200:
            for tourney in res.json().get("data", {}).get("tournaments", []):
                for ev in tourney.get("events", []):
                    home, away = ev.get("homeTeamName"), ev.get("awayTeamName")
                    if not home or not away: continue
                    odds = {}
                    for mkt in ev.get("markets", []):
                        if mkt.get("id") == "1":
                            for out in mkt.get("outcomes", []):
                                if out.get("desc") == "1": odds["Home"] = float(out.get("odds", 0))
                                elif out.get("desc") == "X": odds["Draw"] = float(out.get("odds", 0))
                                elif out.get("desc") == "2": odds["Away"] = float(out.get("odds", 0))
                    if len(odds) == 3:
                        matches.append({
                            "bookie": "MSport", "home": home, "away": away,
                            "norm_key": f"{normalize_team_name(home)}_{normalize_team_name(away)}", "odds": odds
                        })
    except Exception as e:
        logging.warning(f"[MSport Scraper Warning]: {e}")
    return matches

def fetch_odds_api_fallback():
    """Hybrid Fallback: Catches Betway, Betano, and 22Bet via global odds endpoint."""
    if not ODDS_API_KEY:
        return []
    url = f"https://api.the-odds-api.com/v4/sports/soccer_epl/odds/?apiKey={ODDS_API_KEY}&regions=eu,uk&markets=h2h"
    matches = []
    try:
        res = requests.get(url, timeout=8)
        if res.status_code == 200:
            for ev in res.json():
                home, away = ev.get("home_team"), ev.get("away_team")
                norm_key = f"{normalize_team_name(home)}_{normalize_team_name(away)}"
                for bookie in ev.get("bookmakers", []):
                    b_title = bookie.get("title")
                    for mkt in bookie.get("markets", []):
                        if mkt.get("key") == "h2h":
                            odds = {}
                            for out in mkt.get("outcomes", []):
                                if out.get("name") == home: odds["Home"] = float(out.get("price", 0))
                                elif out.get("name") == away: odds["Away"] = float(out.get("price", 0))
                                elif out.get("name") == "Draw": odds["Draw"] = float(out.get("price", 0))
                            if len(odds) == 3:
                                matches.append({
                                    "bookie": b_title, "home": home, "away": away,
                                    "norm_key": norm_key, "odds": odds
                                })
    except Exception as e:
        logging.warning(f"[Odds API Warning]: {e}")
    return matches

# ---------------------------------------------------------------------------
# Aggregator & Multi-Bookie Arbitrage Engine
# ---------------------------------------------------------------------------
def scan_all_bookmakers():
    scrapers = [
        fetch_sportybet,
        fetch_bet9ja,
        fetch_betking,
        fetch_1xbet,
        fetch_msport,
        fetch_odds_api_fallback
    ]

    all_matches = []
    # Execute all scrapers in parallel
    with ThreadPoolExecutor(max_workers=len(scrapers)) as executor:
        futures = [executor.submit(s) for s in scrapers]
        for future in as_completed(futures):
            all_matches.extend(future.result())

    # Aggregate odds across platforms
    aggregated = {}
    for m in all_matches:
        key = m["norm_key"]
        if key not in aggregated:
            aggregated[key] = {
                "display": f"{m['home']} vs {m['away']}",
                "outcomes": {"Home": [], "Draw": [], "Away": []}
            }
        for out_type, price in m["odds"].items():
            if price > 1.0:
                aggregated[key]["outcomes"][out_type].append({"bookie": m["bookie"], "price": price})

    # Find Arbitrage Opportunities
    verified_arbs = []
    for key, data in aggregated.items():
        outs = data["outcomes"]
        if outs["Home"] and outs["Draw"] and outs["Away"]:
            best_home = max(outs["Home"], key=lambda x: x["price"])
            best_draw = max(outs["Draw"], key=lambda x: x["price"])
            best_away = max(outs["Away"], key=lambda x: x["price"])

            implied_sum = (1.0 / best_home["price"]) + (1.0 / best_draw["price"]) + (1.0 / best_away["price"])

            if implied_sum < 1.0:
                roi = round(((1.0 / implied_sum) - 1.0) * 100, 2)
                payout = DEFAULT_BANKROLL / implied_sum
                profit = payout - DEFAULT_BANKROLL

                s_home = round(DEFAULT_BANKROLL / (best_home["price"] * implied_sum), 2)
                s_draw = round(DEFAULT_BANKROLL / (best_draw["price"] * implied_sum), 2)
                s_away = round(DEFAULT_BANKROLL / (best_away["price"] * implied_sum), 2)

                verified_arbs.append({
                    "fixture": data["display"],
                    "roi": roi,
                    "bankroll": DEFAULT_BANKROLL,
                    "profit": round(profit, 2),
                    "stakes": {
                        "Home": {**best_home, "stake": s_home},
                        "Draw": {**best_draw, "stake": s_draw},
                        "Away": {**best_away, "stake": s_away}
                    }
                })

    return verified_arbs

# ---------------------------------------------------------------------------
# Telegram Dispatcher
# ---------------------------------------------------------------------------
def send_telegram(text: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try:
        res = requests.post(url, json=payload, timeout=10)
        return res.status_code == 200
    except Exception as e:
        logging.error(f"Telegram error: {e}")
        return False

def format_alert(arb):
    msg = f"⚡ *ALL-NAIJA ARBITRAGE FOUND* ⚡\n\n"
    msg += f"⚽ *Match*: {arb['fixture']}\n"
    msg += f"📈 *ROI*: *+{arb['roi']}%*\n"
    msg += f"💰 *Bankroll*: ₦{arb['bankroll']:,.2f}\n"
    msg += f"💵 *Net Profit*: *₦{arb['profit']:,.2f}*\n\n"
    msg += f"*RECOMMENDED STAKES*:\n"
    for out, d in arb['stakes'].items():
        msg += f"• *{out}* @ *{d['price']}* ({d['bookie']}) ➔ Wager: *₦{d['stake']:,.2f}*\n"
    return msg

# ---------------------------------------------------------------------------
# Main Execution Loop
# ---------------------------------------------------------------------------
def run_engine():
    logging.info("Scanning SportyBet, Bet9ja, BetKing, 1xBet, MSport & Fallbacks...")
    arbs = scan_all_bookmakers()

    if not arbs:
        logging.info("No cross-bookie arbitrage found across all Nigerian operators.")
        send_telegram("📡 *Multi-Bookie Scanner Active*: Scanned all Nigerian bookmakers. No arbs found.")
        return

    for arb in arbs:
        alert_msg = format_alert(arb)
        send_telegram(alert_msg)

def main():
    threading.Thread(target=start_health_server, daemon=True).start()
    logging.info("Naija Engine Online.")
    while True:
        try:
            run_engine()
        except Exception as e:
            logging.error(f"Error in main loop: {e}")
        time.sleep(SCAN_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()
