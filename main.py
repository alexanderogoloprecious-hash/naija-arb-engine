import os
import time
import logging
import threading
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests

try:
    from duckduckgo_search import DDGS
except ImportError:
    from ddgs import DDGS

from google import genai

# ---------------------------------------------------------------------------
# Configuration & Environment Variables
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
SCAN_INTERVAL_SECONDS = int(os.getenv("SCAN_INTERVAL_SECONDS", 1800))

# ---------------------------------------------------------------------------
# Keep-Alive HTTP Health Check Server
# ---------------------------------------------------------------------------
class KeepAliveServer(BaseHTTPRequestHandler):
    def _send_response(self, text="OK"):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(text.encode("utf-8"))

    def do_GET(self):
        self._send_response("Naija Arb Engine is ONLINE.")

    def do_HEAD(self):
        self._send_response()

    def do_POST(self):
        self._send_response("OK")

    def log_message(self, format, *args):
        return

def start_health_server():
    server = HTTPServer(("0.0.0.0", PORT), KeepAliveServer)
    logging.info(f"Health check server listening on port {PORT}...")
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
        logging.info("Telegram alert delivered successfully.")
        return True
    except Exception as e:
        logging.error(f"Failed to send Telegram message: {e}")
        return False

# ---------------------------------------------------------------------------
# Deterministic Python Arbitrage Scanner
# ---------------------------------------------------------------------------
def fetch_and_detect_real_arbs():
    """Fetches real odds via API and calculates math in Python to prevent hallucinated arbs."""
    if not ODDS_API_KEY:
        logging.warning("ODDS_API_KEY missing. Cannot fetch structured odds.")
        return [], "No Odds API key configured."

    sports = ["soccer_epl", "soccer_spain_la_liga", "soccer_uefa_champs_league"]
    verified_arbs = []
    raw_summary = []

    for sport in sports:
        url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds/"
        params = {
            "apiKey": ODDS_API_KEY,
            "regions": "eu,uk",
            "markets": "h2h,totals",
            "oddsFormat": "decimal"
        }
        try:
            res = requests.get(url, params=params, timeout=10)
            if res.status_code == 200:
                matches = res.json()
                for match in matches:
                    home = match.get("home_team")
                    away = match.get("away_team")
                    commence = match.get("commence_time")

                    best_h2h = {}
                    for b in match.get("bookmakers", []):
                        bookie_name = b.get("title")
                        for m in b.get("markets", []):
                            if m.get("key") == "h2h":
                                for outcome in m.get("outcomes", []):
                                    name = outcome.get("name")
                                    price = outcome.get("price", 0)
                                    if name not in best_h2h or price > best_h2h[name]["price"]:
                                        best_h2h[name] = {"price": price, "bookie": bookie_name}

                    if len(best_h2h) >= 2:
                        implied_sum = sum(1.0 / item["price"] for item in best_h2h.values() if item["price"] > 0)
                        if implied_sum < 1.0:  # Valid Arbitrage Detected
                            roi = ((1.0 / implied_sum) - 1.0) * 100
                            verified_arbs.append({
                                "fixture": f"{home} vs {away}",
                                "commence": commence,
                                "implied_sum": round(implied_sum, 4),
                                "roi": round(roi, 2),
                                "odds": best_h2h
                            })
                    
                    raw_summary.append(f"{home} vs {away} | Odds: {best_h2h}")
        except Exception as e:
            logging.error(f"Error fetching odds for {sport}: {e}")

    return verified_arbs, "\n".join(raw_summary[:10])

# ---------------------------------------------------------------------------
# Zero-Hallucination & Quota-Protected Gemini Scan Loop
# ---------------------------------------------------------------------------
def run_arbitrage_scan():
    now_utc = datetime.now(timezone.utc)
    today_formatted = now_utc.strftime("%A, %B %d, %Y")

    verified_arbs, raw_market_data = fetch_and_detect_real_arbs()

    # CRITICAL QUOTA GUARD: If no arbs exist, send alert directly from Python.
    # Do NOT call Gemini API when there are 0 arbs to conserve daily quota.
    if not verified_arbs:
        logging.info("No arbitrage opportunities found by Python. Skipping Gemini API call to preserve quota.")
        watchlist_msg = "⚠️ *WATCHLIST MODE*: No mathematically valid arbitrage opportunities found across live bookmakers right now. Scanning again in 30 minutes."
        send_telegram_alert(watchlist_msg)
        return

    api_keys = [k.strip() for k in GEMINI_API_KEYS_RAW.split(",") if k.strip()]
    if not api_keys:
        logging.error("No valid GEMINI_API_KEY found.")
        return

    prompt = f"""
    You are 'Naija Arb Scanner'.

    SYSTEM DATE: {today_formatted}

    VERIFIED PYTHON-CALCULATED ARBITRAGE MATCHES:
    {verified_arbs}

    RAW LIVE MARKET DATA FEED:
    {raw_market_data}

    STRICT OPERATIONAL RULES:
    1. ZERO HALLUCINATION PERMITTED: DO NOT invent matches, scores, team names, bookmaker names, or odds numbers under any circumstances.
    2. ONLY format the exact teams and odds provided in the VERIFIED DATA feed above.
    3. DO NOT use LaTeX syntax ($ or \\frac).
    4. Format the final output clearly for Telegram using bold header lines.
    """

    # Model endpoints list with robust active fallbacks
    valid_models = ["gemini-3.6-flash", "gemini-3.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]

    for key in api_keys:
        client = genai.Client(api_key=key)

        for model_name in valid_models:
            for attempt in range(1, 3):
                try:
                    logging.info(f"Formatting real arbitrage alert using {model_name} (Attempt {attempt})...")
                    response = client.models.generate_content(
                        model=model_name,
                        contents=prompt
                    )

                    if response.text and response.text.strip():
                        send_telegram_alert(response.text.strip())
                        return
                except Exception as e:
                    err_msg = str(e)
                    logging.warning(f"Error on {model_name} (Attempt {attempt}): {err_msg}")
                    
                    if "404" in err_msg or "NOT_FOUND" in err_msg:
                        logging.warning(f"Model {model_name} not available. Skipping immediately...")
                        break  # Immediately skip deprecated models
                    elif "503" in err_msg or "UNAVAILABLE" in err_msg or "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                        logging.info("Rate limit or service busy hit. Waiting 25 seconds for quota window reset...")
                        time.sleep(25)  # Pause to clear Google's 22s retry window
                    else:
                        time.sleep(3)

    logging.error("All model execution attempts failed.")

# ---------------------------------------------------------------------------
# Main Execution Loop
# ---------------------------------------------------------------------------
def main():
    threading.Thread(target=start_health_server, daemon=True).start()
    logging.info("Naija Arb Engine started with Zero-Hallucination and Quota-Protection safeguards.")

    while True:
        try:
            run_arbitrage_scan()
        except Exception as e:
            logging.error(f"Unexpected exception in main loop: {e}")

        logging.info(f"Sleeping for {SCAN_INTERVAL_SECONDS} seconds...")
        time.sleep(SCAN_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()
