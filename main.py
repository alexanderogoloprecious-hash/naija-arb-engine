import os
import time
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests

# ---------------------------------------------------------------------------
# 1. System Logging Configuration
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# ---------------------------------------------------------------------------
# 2. Environment Variables
# ---------------------------------------------------------------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
ODDS_API_KEY = os.getenv("ODDS_API_KEY")
PORT = int(os.getenv("PORT", 10000))
SCAN_INTERVAL_SECONDS = int(os.getenv("SCAN_INTERVAL_SECONDS", 300))  # Default 5 mins
DEFAULT_BANKROLL = float(os.getenv("DEFAULT_BANKROLL", 100000))        # Default ₦100,000

# Targeted Football Sports Keys on The Odds API
SPORT_KEYS = [
    "soccer_epl",               # English Premier League
    "soccer_spain_la_liga",     # Spanish La Liga
    "soccer_italy_serie_a",     # Italian Serie A
    "soccer_germany_bundesliga",# German Bundesliga
    "soccer_france_ligue_one",  # French Ligue 1
    "soccer_uefa_champs_league" # UEFA Champions League
]

# ---------------------------------------------------------------------------
# 3. Health Check Server (Render & UptimeRobot Compliant)
# ---------------------------------------------------------------------------
class HealthServer(BaseHTTPRequestHandler):
    def _send_ok(self, text="Naija Odds-API Arb Engine is ONLINE."):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(text.encode("utf-8"))

    def do_GET(self):
        self._send_ok()

    def do_HEAD(self):
        self._send_ok()

    def do_POST(self):
        self._send_ok()

    def log_message(self, format, *args):
        return

def start_health_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthServer)
    logging.info(f"Health server active on port {PORT}...")
    server.serve_forever()

# ---------------------------------------------------------------------------
# 4. Telegram Dispatcher
# ---------------------------------------------------------------------------
def send_telegram_alert(message: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logging.error("Telegram credentials missing in environment variables.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }

    try:
        res = requests.post(url, json=payload, timeout=12)
        if res.status_code == 200:
            logging.info("Telegram notification sent successfully.")
            return True
        else:
            logging.error(f"Telegram error ({res.status_code}): {res.text}")
            return False
    except Exception as e:
        logging.error(f"Failed to connect to Telegram API: {e}")
        return False

# ---------------------------------------------------------------------------
# 5. Fetch Odds from The Odds API
# ---------------------------------------------------------------------------
def fetch_league_odds(sport_key: str):
    """Fetches head-to-head (1X2) market odds for a given sport league."""
    if not ODDS_API_KEY:
        logging.error("ODDS_API_KEY environment variable is not set.")
        return []

    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds/"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": "eu,uk",
        "markets": "h2h",
        "dateFormat": "iso"
    }

    try:
        res = requests.get(url, params=params, timeout=10)
        if res.status_code == 200:
            return res.json()
        else:
            logging.warning(f"Failed fetching {sport_key} ({res.status_code}): {res.text}")
            return []
    except Exception as e:
        logging.error(f"Error fetching odds for {sport_key}: {e}")
        return []

# ---------------------------------------------------------------------------
# 6. Arbitrage Detection & Calculation Engine
# ---------------------------------------------------------------------------
def process_arbitrage_scan():
    if not ODDS_API_KEY:
        logging.error("Cannot run scan: ODDS_API_KEY is missing.")
        return

    logging.info("Starting multi-league scan via The Odds API...")
    
    # Fetch all configured leagues concurrently
    raw_results = []
    with ThreadPoolExecutor(max_workers=len(SPORT_KEYS)) as executor:
        futures = [executor.submit(fetch_league_odds, key) for key in SPORT_KEYS]
        for future in futures:
            data = future.result()
            if data:
                raw_results.extend(data)

    if not raw_results:
        logging.info("Scan completed: No match data returned.")
        return

    verified_arbs = []
    total_matches_scanned = len(raw_results)

    for event in raw_results:
        home_team = event.get("home_team")
        away_team = event.get("away_team")
        fixture_name = f"{home_team} vs {away_team}"

        outcomes = {"Home": [], "Draw": [], "Away": []}

        # Collect 1x2 prices across all bookmakers for this event
        for bookmaker in event.get("bookmakers", []):
            b_title = bookmaker.get("title")
            for market in bookmaker.get("markets", []):
                if market.get("key") == "h2h":
                    for outcome in market.get("outcomes", []):
                        name = outcome.get("name")
                        price = float(outcome.get("price", 0))
                        if price > 1.0:
                            if name == home_team:
                                outcomes["Home"].append({"bookie": b_title, "price": price})
                            elif name == away_team:
                                outcomes["Away"].append({"bookie": b_title, "price": price})
                            elif name == "Draw":
                                outcomes["Draw"].append({"bookie": b_title, "price": price})

        # Check if we have valid odds for all 3 outcomes
        if outcomes["Home"] and outcomes["Draw"] and outcomes["Away"]:
            best_home = max(outcomes["Home"], key=lambda x: x["price"])
            best_draw = max(outcomes["Draw"], key=lambda x: x["price"])
            best_away = max(outcomes["Away"], key=lambda x: x["price"])

            # Calculate total implied probability (Margin)
            implied_sum = (1.0 / best_home["price"]) + (1.0 / best_draw["price"]) + (1.0 / best_away["price"])

            # Arbitrage exists if implied probability sum < 1.0 (Margin < 100%)
            # We filter for realistic ROI between 0.5% and 15% to avoid bad line errors
            if implied_sum < 1.0:
                roi = round(((1.0 / implied_sum) - 1.0) * 100, 2)
                if 0.5 <= roi <= 15.0:
                    payout = DEFAULT_BANKROLL / implied_sum
                    profit = payout - DEFAULT_BANKROLL

                    stake_home = round(DEFAULT_BANKROLL / (best_home["price"] * implied_sum), 2)
                    stake_draw = round(DEFAULT_BANKROLL / (best_draw["price"] * implied_sum), 2)
                    stake_away = round(DEFAULT_BANKROLL / (best_away["price"] * implied_sum), 2)

                    verified_arbs.append({
                        "fixture": fixture_name,
                        "roi": roi,
                        "bankroll": DEFAULT_BANKROLL,
                        "profit": round(profit, 2),
                        "stakes": {
                            "Home": {**best_home, "stake": stake_home},
                            "Draw": {**best_draw, "stake": stake_draw},
                            "Away": {**best_away, "stake": stake_away}
                        }
                    })

    logging.info(f"Scan complete: Scanned {total_matches_scanned} matches. Found {len(verified_arbs)} surebet(s).")

    # Send alerts if arbs are found
    for arb in verified_arbs:
        msg = f"⚡ *SUREBET OPPORTUNITY DETECTED* ⚡\n\n"
        msg += f"⚽ *Match*: {arb['fixture']}\n"
        msg += f"📈 *ROI*: *+{arb['roi']}%*\n"
        msg += f"💰 *Total Bankroll*: ₦{arb['bankroll']:,.2f}\n"
        msg += f"💵 *Net Profit*: *₦{arb['profit']:,.2f}*\n\n"
        msg += f"*STAKE DISTRIBUTION*:\n"
        for option, details in arb["stakes"].items():
            msg += f"• *{option}* @ *{details['price']}* ({details['bookie']}) ➔ Bet: *₦{details['stake']:,.2f}*\n"

        send_telegram_alert(msg)

# ---------------------------------------------------------------------------
# 7. Main Execution Loop
# ---------------------------------------------------------------------------
def main():
    # Start background health server for Render & UptimeRobot
    threading.Thread(target=start_health_server, daemon=True).start()

    logging.info("Naija Arb Engine (Solution B) initialized.")
    send_telegram_alert("🚀 **Naija Arb Engine** online! Monitoring major football leagues for arbitrage...")

    while True:
        try:
            process_arbitrage_scan()
        except Exception as e:
            logging.error(f"Execution loop error: {e}")

        logging.info(f"Waiting {SCAN_INTERVAL_SECONDS} seconds for next scan...")
        time.sleep(SCAN_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()
