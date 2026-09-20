import os
import time
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests
from ddgs import DDGS
from google import genai

# ---------------------------------------------------------------------------
# Logging Configuration
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# ---------------------------------------------------------------------------
# Environment Variables
# ---------------------------------------------------------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
PORT = int(os.getenv("PORT", 10000))

# ---------------------------------------------------------------------------
# Health Check Server
# ---------------------------------------------------------------------------
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Naija Arb Engine is operational.")

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()

    def log_message(self, format, *args):
        return

def start_health_server():
    server_address = ("", PORT)
    httpd = HTTPServer(server_address, HealthCheckHandler)
    logging.info(f"Health check server running on port {PORT}...")
    httpd.serve_forever()

# ---------------------------------------------------------------------------
# Telegram Dispatcher
# ---------------------------------------------------------------------------
def send_telegram_alert(message: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logging.error("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }

    try:
        response = requests.post(url, json=payload, timeout=15)
        if response.status_code == 200:
            logging.info("Telegram alert delivered successfully.")
            return True
        else:
            payload.pop("parse_mode", None)
            requests.post(url, json=payload, timeout=15)
            logging.info("Telegram alert sent via plain text fallback.")
            return True
    except Exception as e:
        logging.error(f"Telegram connection error: {e}")
        return False

# ---------------------------------------------------------------------------
# Search Context Fetcher
# ---------------------------------------------------------------------------
def fetch_live_market_snippets():
    query = "Nigerian bookmakers odds Bet9ja SportyBet 1xBet BetKing Betway Betano MSport live football matches today"
    try:
        logging.info("Fetching live odds snippets via DuckDuckGo...")
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=8))
            snippets = [r.get("body", "") for r in results if r.get("body")]
            if snippets:
                return "\n".join(snippets)
    except Exception as e:
        logging.warning(f"DuckDuckGo search error: {e}")
    
    return "Standard odds monitoring active across Nigerian bookmakers."

# ---------------------------------------------------------------------------
# Gemini Scanner Engine with 503 Retry & Model Fallback
# ---------------------------------------------------------------------------
def run_arbitrage_scan():
    if not GEMINI_API_KEY:
        logging.error("GEMINI_API_KEY is not configured.")
        return

    client = genai.Client(api_key=GEMINI_API_KEY)
    live_context = fetch_live_market_snippets()

    prompt = f"""
    You are 'Naija Arb Scanner', an automated sports arbitrage monitoring system for Nigerian bookmakers:
    Bet9ja, SportyBet, 1xBet, BetKing, Betway, Betano, MSport, 22Bet, and Melbet.

    LIVE MARKET CONTEXT DATA:
    {live_context}

    Task:
    1. Analyze current live and upcoming football/sports matches for odds discrepancies and arbitrage opportunities across Nigerian operators.
    2. Target NPFL, EPL, La Liga, UEFA Champions League, and major international leagues.

    Formatting Rules for Output:
    - DO NOT use Markdown headers (#, ##, ###). Use bold line tags like **Naija Sports Surebet Report**.
    - DO NOT output LaTeX symbols ($ or \\frac). Use standard math like (1 / 2.80) + (1 / 2.70).
    - If high-profit surebets (>= 30% ROI) are detected, mark the top banner as:
      **STATUS**: 🚨 HIGH-PROFIT SUREBET FOUND (>= 30% ROI)
    - Always output exact arithmetic check, profit margin ROI %, and a Stake Breakdown based on ₦10,000 total capital.
    - Include a **MARKET DISCREPANCY WATCHLIST** showing tight odds spreads across operators.
    - End with **EXECUTION RULES FOR NIGERIAN TRADERS**.
    """

    # Models list to handle high demand / 503 server spikes
    candidate_models = ["gemini-3.6-flash", "gemini-2.5-flash"]

    for model_name in candidate_models:
        for attempt in range(1, 3):
            try:
                logging.info(f"Running Gemini ({model_name}) analysis (Attempt {attempt})...")
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt
                )

                if response.text and response.text.strip():
                    send_telegram_alert(response.text.strip())
                    return
                else:
                    logging.warning("Gemini API returned an empty response.")
                    return

            except Exception as e:
                error_str = str(e)
                if "503" in error_str or "UNAVAILABLE" in error_str:
                    logging.warning(f"Model {model_name} overloaded (503). Waiting 10s...")
                    time.sleep(10)
                else:
                    logging.error(f"Error with {model_name}: {e}")
                    break

    logging.error("All Gemini model candidates are currently experiencing server load. Will retry on next cycle.")

# ---------------------------------------------------------------------------
# Main Loop
# ---------------------------------------------------------------------------
def main():
    threading.Thread(target=start_health_server, daemon=True).start()

    logging.info("Naija Arb Engine started successfully.")
    send_telegram_alert("⚡ **Naija Arb Engine** online and monitoring live odds.")

    while True:
        try:
            run_arbitrage_scan()
        except Exception as e:
            logging.error(f"Unexpected loop exception: {e}")

        logging.info("Cycle complete. Sleeping for 15 minutes...")
        time.sleep(900)

if __name__ == "__main__":
    main()
