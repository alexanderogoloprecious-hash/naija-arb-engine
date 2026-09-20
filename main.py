import os
import re
import time
import logging
import threading
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests

from google import genai

# ---------------------------------------------------------------------------
# Environment Configuration
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
SCAN_INTERVAL_SECONDS = int(os.getenv("SCAN_INTERVAL_SECONDS", 300))  # Default 5 minutes
DEFAULT_BANKROLL = float(os.getenv("DEFAULT_BANKROLL", 100000))        # Default ₦100,000

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 12; Mobile) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

# ---------------------------------------------------------------------------
# Web Server for Render Health Checks
# ---------------------------------------------------------------------------
class KeepAliveServer(BaseHTTPRequestHandler):
    def _send_response(self, text="OK"):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(text.encode("utf-8"))

    def do_GET(self):
        self._send_response("Naija Arb Engine v4.0 is ONLINE.")

    def do_HEAD(self):
        self._send_response()

    def do_POST(self):
        self._send_response("OK")

    def log_message(self, format, *args):
        return

def start_health_server():
    server = HTTPServer(("0.0.0.0", PORT), KeepAliveServer)
    logging.info(f"Health check server running on port {PORT}...")
    server.serve_forever()

# ---------------------------------------------------------------------------
# Telegram Dispatcher
# ---------------------------------------------------------------------------
def send_telegram_alert(text: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logging.error("Telegram credentials missing!")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }

    try:
        res = requests.post(url, json=payload, timeout=15)
        if res.status_code != 200:
            payload.pop("parse_mode", None)
            requests.post(url, json=payload, timeout=15)
        logging.info("Telegram notification sent successfully.")
        return True
    except Exception as e:
        logging.error(f"Failed to send Telegram message: {e}")
        return False

# ---------------------------------------------------------------------------
# Team Name Normalizer for Cross-Bookie Matching
# ---------------------------------------------------------------------------
def normalize_name(name: str) -> str:
    """Standardizes team names so 'Chelsea FC' matches 'Chelsea' across bookies."""
    name = name.lower()
    for word in [" fc", "fc ", " cf", "cf ", " united", " utd", " town", " city"]:
        name = name.replace(word, "")
    return re.sub(r'[^a-z0-9]', '', name)

# ---------------------------------------------------------------------------
# Direct Bookmaker Scrapers
# ---------------------------------------------------------------------------
def fetch_sportybet_odds():
    """Direct JSON API Scraper for SportyBet Nigeria."""
    url = "https://www.sportybet.com/api/ng/factsCenter/upcomingEvents"
    params = {"sportId": "sr:sport:1", "marketId": "1", "pageSize": 40}
    headers = {**DEFAULT_HEADERS, "Referer": "https://www.sportybet.com/ng/"}

    matches = []
    try:
        res = requests.get(url, params=params, headers=headers, timeout=10)
        if res.status_code == 200:
            tournaments = res.json().get("data", {}).get("tournaments", [])
            for tourney in tournaments:
                for event in tourney.get("events", []):
                    home = event.get("homeTeamName")
                    away = event.get("awayTeamName")
                    if not home or not away:
                        continue

                    odds = {}
                    for market in event.get("markets", []):
                        if market.get("id") == "1":
                            for outcome in market.get("outcomes", []):
                                desc = outcome.get("desc")
                                price = float(outcome.get("odds", 0))
                                if desc == "1": odds["Home"] = price
                                elif desc == "X": odds["Draw"] = price
                                elif desc == "2": odds["Away"] = price

                    if len(odds) == 3:
                        matches.append({
                            "bookmaker": "SportyBet",
                            "home": home,
                            "away": away,
                            "norm_key": f"{normalize_name(home)}_{normalize_name(away)}",
                            "odds": odds
                        })
            logging.info(f"[SportyBet] Fetched {len(matches)} matches.")
    except Exception as e:
        logging.error(f"[SportyBet Scraper Error]: {e}")
    return matches

def fetch_bet9ja_odds():
    """Direct JSON API Scraper for Bet9ja Nigeria."""
    url = "https://sports.bet9ja.com/desktop/feapi/Palimpsest/GetPrematchEvents"
    params = {"sportId": 1, "dayOffset": 0, "pageSize": 40}
    headers = {**DEFAULT_HEADERS, "Referer": "https://sports.bet9ja.com/"}

    matches = []
    try:
        res = requests.get(url, params=params, headers=headers, timeout=10)
        if res.status_code == 200:
            events = res.json().get("data", {}).get("events", [])
            for event in events:
                home = event.get("home_team")
                away = event.get("away_team")
                if not home or not away:
                    continue

                raw_odds = event.get("odds", {})
                odds = {
                    "Home": float(raw_odds.get("1", 0)),
                    "Draw": float(raw_odds.get("X", 0)),
                    "Away": float(raw_odds.get("2", 0))
                }

                if all(v > 1.0 for v in odds.values()):
                    matches.append({
                        "bookmaker": "Bet9ja",
                        "home": home,
                        "away": away,
                        "norm_key": f"{normalize_name(home)}_{normalize_name(away)}",
                        "odds": odds
                    })
            logging.info(f"[Bet9ja] Fetched {len(matches)} matches.")
    except Exception as e:
        logging.error(f"[Bet9ja Scraper Error]: {e}")
    return matches

# ---------------------------------------------------------------------------
# Cross-Bookmaker Arbitrage Calculation Engine
# ---------------------------------------------------------------------------
def calculate_arbitrage():
    sportybet_matches = fetch_sportybet_odds()
    bet9ja_matches = fetch_bet9ja_odds()

    # Aggregate odds across platforms
    aggregated = {}

    def ingest(matches_list):
        for m in matches_list:
            key = m["norm_key"]
            if key not in aggregated:
                aggregated[key] = {
                    "display_fixture": f"{m['home']} vs {m['away']}",
                    "outcomes": {"Home": [], "Draw": [], "Away": []}
                }
            for outcome_type, price in m["odds"].items():
                if price > 1.0:
                    aggregated[key]["outcomes"][outcome_type].append({
                        "bookmaker": m["bookmaker"],
                        "price": price
                    })

    ingest(sportybet_matches)
    ingest(bet9ja_matches)

    verified_arbs = []

    for key, data in aggregated.items():
        outcomes = data["outcomes"]
        if outcomes["Home"] and outcomes["Draw"] and outcomes["Away"]:
            best_home = max(outcomes["Home"], key=lambda x: x["price"])
            best_draw = max(outcomes["Draw"], key=lambda x: x["price"])
            best_away = max(outcomes["Away"], key=lambda x: x["price"])

            implied_sum = (1.0 / best_home["price"]) + (1.0 / best_draw["price"]) + (1.0 / best_away["price"])

            # Arbitrage Condition: Implied Probability Sum < 1.0
            if implied_sum < 1.0:
                roi = ((1.0 / implied_sum) - 1.0) * 100
                total_payout = DEFAULT_BANKROLL / implied_sum
                net_profit = total_payout - DEFAULT_BANKROLL

                # Calculate Exact Stake Breakdown
                stake_home = round((DEFAULT_BANKROLL / (best_home["price"] * implied_sum)), 2)
                stake_draw = round((DEFAULT_BANKROLL / (best_draw["price"] * implied_sum)), 2)
                stake_away = round((DEFAULT_BANKROLL / (best_away["price"] * implied_sum)), 2)

                verified_arbs.append({
                    "fixture": data["display_fixture"],
                    "roi": round(roi, 2),
                    "bankroll": DEFAULT_BANKROLL,
                    "net_profit": round(net_profit, 2),
                    "best_outcomes": {
                        "Home": {**best_home, "stake": stake_home},
                        "Draw": {**best_draw, "stake": stake_draw},
                        "Away": {**best_away, "stake": stake_away}
                    }
                })

    return verified_arbs

# ---------------------------------------------------------------------------
# Formatting & Execution Loop
# ---------------------------------------------------------------------------
def format_arb_telegram_message(arb):
    """Fallback Python Telegram formatter if Gemini is resting or out of quota."""
    msg = f"🚨 *ARBITRAGE OPPORTUNITY FOUND* 🚨\n\n"
    msg += f"⚽ *Match*: {arb['fixture']}\n"
    msg += f"📈 *ROI*: *+{arb['roi']}%*\n"
    msg += f"💰 *Bankroll*: ₦{arb['bankroll']:,.2f}\n"
    msg += f"💵 *Expected Net Profit*: *₦{arb['net_profit']:,.2f}*\n\n"
    msg += f"*STAKE BREAKDOWN*:\n"
    
    for outcome, data in arb['best_outcomes'].items():
        msg += f"• *{outcome}* @ *{data['price']}* ({data['bookmaker']}) ➔ Stake: *₦{data['stake']:,.2f}*\n"
    
    return msg

def run_scan():
    logging.info("Starting combined market scan...")
    arbs = calculate_arbitrage()

    # QUOTA PROTECTION: If no arbs found, alert via Telegram directly. Do NOT call Gemini API.
    if not arbs:
        logging.info("No arbitrage opportunities found. Skipping Gemini API call to preserve quota.")
        send_telegram_alert("⚠️ *WATCHLIST MODE*: Scanned SportyBet and Bet9ja. No cross-market arbitrage found. Rescanning shortly.")
        return

    # If arbs exist, process them
    for arb in arbs:
        python_formatted_msg = format_arb_telegram_message(arb)
        api_keys = [k.strip() for k in GEMINI_API_KEYS_RAW.split(",") if k.strip()]

        if not api_keys:
            send_telegram_alert(python_formatted_msg)
            continue

        # Try polishing message via Gemini API
        gemini_success = False
        valid_models = ["gemini-3.6-flash", "gemini-3.5-flash", "gemini-2.0-flash"]
        
        prompt = f"Reformat this arbitrage alert clearly for Telegram without changing any numbers:\n\n{python_formatted_msg}"

        for key in api_keys:
            if gemini_success: break
            client = genai.Client(api_key=key)

            for model_name in valid_models:
                try:
                    response = client.models.generate_content(model=model_name, contents=prompt)
                    if response.text and response.text.strip():
                        send_telegram_alert(response.text.strip())
                        gemini_success = True
                        break
                except Exception as e:
                    logging.warning(f"Gemini formatting failed on {model_name}: {e}")
                    time.sleep(2)

        # Fallback to pure Python message if Gemini API failed or was rate-limited
        if not gemini_success:
            send_telegram_alert(python_formatted_msg)

# ---------------------------------------------------------------------------
# Main Execution Loop
# ---------------------------------------------------------------------------
def main():
    threading.Thread(target=start_health_server, daemon=True).start()
    logging.info("Naija Arb Engine v4.0 Started.")

    while True:
        try:
            run_scan()
        except Exception as e:
            logging.error(f"Unexpected error in main loop: {e}")

        logging.info(f"Sleeping for {SCAN_INTERVAL_SECONDS} seconds...")
        time.sleep(SCAN_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()
