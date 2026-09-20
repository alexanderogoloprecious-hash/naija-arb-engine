import os
import time
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests
from google import genai
from google.genai import types

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
# HTTP Keep-Alive Health Server (Render & UptimeRobot Compliant)
# ---------------------------------------------------------------------------
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        """Responds to GET health checks from Render."""
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Naija Arb Engine is UP and operational.")

    def do_HEAD(self):
        """Responds to HEAD ping checks from UptimeRobot (prevents HTTP 501)."""
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()

    def log_message(self, format, *args):
        """Suppresses default HTTP request logging to keep output clean."""
        return

def start_health_server():
    server_address = ("", PORT)
    httpd = HTTPServer(server_address, HealthCheckHandler)
    logging.info(f"Health check server listening on port {PORT}...")
    httpd.serve_forever()

# ---------------------------------------------------------------------------
# Telegram Delivery System
# ---------------------------------------------------------------------------
def send_telegram_alert(message: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logging.error("Telegram Bot Token or Chat ID is missing in environment variables.")
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
            logging.error(f"Failed to send Telegram alert ({response.status_code}): {response.text}")
            return False
    except Exception as e:
        logging.error(f"Error during Telegram API request: {e}")
        return False

# ---------------------------------------------------------------------------
# Gemini Sports Arbitrage Engine
# ---------------------------------------------------------------------------
def run_arbitrage_scan():
    if not GEMINI_API_KEY:
        logging.error("GEMINI_API_KEY is not configured.")
        return

    client = genai.Client(api_key=GEMINI_API_KEY)

    prompt = """
    You are 'Naija Arb Scanner', an automated sports arbitrage monitoring system for Nigerian bookmakers (Bet9ja, SportyBet, 1xBet, BetKing, Betway, Betano, MSport, 22Bet, Melbet).

    Task:
    1. Search current live and upcoming football/sports matches across Nigerian operators for odds discrepancies and arbitrage opportunities.
    2. Focus on NPFL, EPL, La Liga, UEFA Champions League, and major global leagues.

    Formatting Rules for Output:
    - DO NOT use Markdown headers (#, ##, ###). Use bold line tags like **Naija Sports Surebet Report**.
    - DO NOT output raw LaTeX symbols ($ or \\frac). Use plain math notation like (1 / 2.80) + (1 / 2.70).
    - If high-profit surebets (>= 30% ROI) are detected, mark the top banner as:
      **STATUS**: 🚨 HIGH-PROFIT SUREBET FOUND (>= 30% ROI)
    - Always output exact arithmetic check, profit margin ROI %, and a Stake Breakdown based on ₦10,000 total capital.
    - Include a **MARKET DISCREPANCY WATCHLIST** highlighting tight odds spreads or cross-bookmaker variance.
    - End with **EXECUTION RULES FOR NIGERIAN TRADERS**.
    """

    try:
        logging.info("Starting new odds scan cycle...")
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[{"google_search": {}}]
            )
        )

        if response.text and response.text.strip():
            report = response.text.strip()
            send_telegram_alert(report)
        else:
            logging.warning("Gemini engine returned an empty response.")

    except Exception as e:
        logging.error(f"Error during Gemini arbitrage scan: {e}")

# ---------------------------------------------------------------------------
# Main Execution Loop
# ---------------------------------------------------------------------------
def main():
    # Start KeepAlive server in a daemon background thread
    server_thread = threading.Thread(target=start_health_server, daemon=True)
    server_thread.start()

    # Initial boot alert
    logging.info("Naija Arb Engine initialized successfully.")
    send_telegram_alert("🚀 **Naija Arb Engine** online and monitoring odds...")

    # Infinite scanning loop (runs every 15 minutes)
    while True:
        try:
            run_arbitrage_scan()
        except Exception as e:
            logging.error(f"Unexpected loop exception: {e}")

        logging.info("Sleeping for 15 minutes...")
        time.sleep(900)

if __name__ == "__main__":
    main()
