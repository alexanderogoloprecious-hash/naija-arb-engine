import os
import time
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests
from google import genai
from google.genai import types

# ---------------------------------------------------------------------------
# 1. System Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# ---------------------------------------------------------------------------
# 2. Environment Variables & Configurations
# ---------------------------------------------------------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
PORT = int(os.getenv("PORT", 10000))

# ---------------------------------------------------------------------------
# 3. HTTP Health Check Server (Render & UptimeRobot Compliant)
# ---------------------------------------------------------------------------
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        """Responds to GET health checks from Render."""
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Naija Arb Engine is operational.")

    def do_HEAD(self):
        """Responds to HEAD pings from UptimeRobot (prevents 501 errors)."""
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()

    def log_message(self, format, *args):
        """Suppresses HTTP request logs to keep Render console output clean."""
        return

def start_health_server():
    server_address = ("", PORT)
    httpd = HTTPServer(server_address, HealthCheckHandler)
    logging.info(f"Health check server running on port {PORT}...")
    httpd.serve_forever()

# ---------------------------------------------------------------------------
# 4. Telegram Alert Dispatcher
# ---------------------------------------------------------------------------
def send_telegram_alert(message: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logging.error("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID environment variables missing.")
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
            logging.info("Telegram notification sent successfully.")
            return True
        else:
            logging.error(f"Telegram dispatch failed ({response.status_code}): {response.text}")
            return False
    except Exception as e:
        logging.error(f"Error connecting to Telegram API: {e}")
        return False

# ---------------------------------------------------------------------------
# 5. Gemini 3.6 Flash Scanning Engine
# ---------------------------------------------------------------------------
def run_arbitrage_scan():
    if not GEMINI_API_KEY:
        logging.error("GEMINI_API_KEY is not set.")
        return

    client = genai.Client(api_key=GEMINI_API_KEY)

    prompt = """
    You are 'Naija Arb Scanner', an automated sports arbitrage monitoring system for Nigerian bookmakers (Bet9ja, SportyBet, 1xBet, BetKing, Betway, Betano, MSport, 22Bet, Melbet).

    Task:
    1. Search active and upcoming football/sports matches across Nigerian operators for odds discrepancies and arbitrage opportunities.
    2. Target NPFL, EPL, La Liga, UEFA Champions League, and major international leagues.

    Formatting Rules for Output:
    - DO NOT use Markdown headers (#, ##, ###). Use bold text like **Naija Sports Surebet Report**.
    - DO NOT output LaTeX symbols ($ or \\frac). Use standard math like (1 / 2.80) + (1 / 2.70).
    - If high-profit surebets (>= 30% ROI) are detected, set top status to:
      **STATUS**: 🚨 HIGH-PROFIT SUREBET FOUND (>= 30% ROI)
    - Provide exact implied probability math, profit ROI %, and stake sizing for a ₦10,000 total bankroll.
    - Include a **MARKET DISCREPANCY WATCHLIST** showing tight odds spreads across operators.
    - Conclude with **EXECUTION RULES FOR NIGERIAN TRADERS**.
    """

    max_retries = 3
    delay = 15  # Initial wait time in seconds for quota reset

    for attempt in range(1, max_retries + 1):
        try:
            logging.info(f"Executing market scan cycle (Attempt {attempt}/{max_retries})...")
            
            # Using client.chats.create to eliminate AFC deprecation warnings
            chat = client.chats.create(
                model="gemini-3.6-flash",
                config=types.GenerateContentConfig(
                    tools=[{"google_search": {}}]
                )
            )
            response = chat.send_message(prompt)

            if response.text and response.text.strip():
                report = response.text.strip()
                send_telegram_alert(report)
                return
            else:
                logging.warning("Gemini API returned an empty output.")
                return

        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                if attempt < max_retries:
                    logging.warning(f"Quota rate limit reached (429). Retrying in {delay} seconds...")
                    time.sleep(delay)
                    delay *= 2  # Exponential backoff
                else:
                    logging.error("Max retries reached. Skipping scan cycle due to API quota limits.")
            else:
                logging.error(f"Uncaught error during arbitrage scan: {e}")
                break

# ---------------------------------------------------------------------------
# 6. Main Application Entry Point
# ---------------------------------------------------------------------------
def main():
    # Run Health Check server in background daemon thread
    server_thread = threading.Thread(target=start_health_server, daemon=True)
    server_thread.start()

    # System Startup Message
    logging.info("Naija Arb Engine started successfully.")
    send_telegram_alert("⚡ **Naija Arb Engine** online. Monitoring live odds...")

    # Main scanning loop (15-minute interval)
    while True:
        try:
            run_arbitrage_scan()
        except Exception as e:
            logging.error(f"Execution loop crash prevented: {e}")

        logging.info("Cycle complete. Next scan in 15 minutes...")
        time.sleep(900)

if __name__ == "__main__":
    main()
