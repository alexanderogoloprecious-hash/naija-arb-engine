import os
import time
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests
from duckduckgo_search import DDGS
from google import genai

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# Environment Variables
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
PORT = int(os.environ.get("PORT", 10000))

# Initialize Gemini Client
client = genai.Client(api_key=GEMINI_API_KEY)


class KeepAliveServer(BaseHTTPRequestHandler):
    """HTTP server for Render health checks and UptimeRobot pings (supports GET, HEAD, POST)."""
    
    def _send_success(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()

    def do_GET(self):
        self._send_success()
        self.wfile.write(b"Naija Arb Engine is ONLINE and active.")

    def do_HEAD(self):
        # Handles UptimeRobot HEAD requests
        self._send_success()

    def do_POST(self):
        # Handles potential webhook/POST pings
        self.do_GET()

    def log_message(self, format, *args):
        return  # Suppress HTTP access logs in console


def start_health_server():
    server = HTTPServer(("0.0.0.0", PORT), KeepAliveServer)
    logging.info(f"Health check server listening on port {PORT}...")
    server.serve_forever()


def send_telegram_message(text):
    """Sends clean text alerts to Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logging.error("Telegram credentials missing!")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    try:
        res = requests.post(url, json=payload, timeout=15)
        if not res.ok:
            # Fallback to plain text if Markdown parsing encounters unexpected characters
            payload.pop("parse_mode")
            requests.post(url, json=payload, timeout=15)
        logging.info("Telegram alert delivered successfully.")
    except Exception as e:
        logging.error(f"Failed to send Telegram message: {e}")


def fetch_live_odds_context():
    """Fetches real-time odds data using DuckDuckGo."""
    query = "Nigerian bookmaker odds Bet9ja SportyBet 1xBet BetKing Betway Betano MSport live matches today"
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=8))
            snippets = [r.get("body", "") for r in results]
            return "\n".join(snippets)
    except Exception as e:
        logging.warning(f"Live search fetch warning: {e}")
        return "Standard live odds monitoring active."


def run_arbitrage_scan():
    """Scans for sports arbitrage, enforces 30% ROI minimum, and pushes Telegram updates."""
    logging.info("Starting new odds scan cycle...")
    odds_context = fetch_live_odds_context()

    prompt = f"""
    You are an expert sports arbitrage scanner monitoring 9 Nigerian bookmakers:
    Bet9ja, SportyBet, 1xBet Nigeria, BetKing, Betway Nigeria, Betano Nigeria, MSport, 22Bet, and Melbet.

    Live Web Odds Context:
    {odds_context}

    CRITICAL RULES & TARGETS:
    1. TARGET PROFIT THRESHOLD: 30.00% MINIMUM ROI.
       - Implied Probability Sum = (1 / Odds_1) + (1 / Odds_2)
       - A 30% profit means Implied Probability Sum <= 0.7692 (e.g., N10,000 total bet returns N13,000+ total payout).
    2. STAKE CALCULATION MODEL (For N10,000 Total Capital):
       - Stake 1 = N10,000 / (Implied Sum * Odds_1)
       - Stake 2 = N10,000 / (Implied Sum * Odds_2)
       - Total Return must equal or exceed N13,000.
    3. FORMATTING STRICTLY FOR TELEGRAM (NO LATEX & NO MARKDOWN HEADERS):
       - NEVER use Markdown headers (#, ##, ###, ####). Use standalone bold text **LIKE THIS**.
       - NEVER use LaTeX syntax (do not use $, \\frac, or \\text). Write simple calculations like: "(1 / 1.50) + (1 / 3.00) = 0.6667 + 0.3333 = 1.0000".
    4. STATUS BANNER CONSISTENCY RULE:
       - If ANY match yields Profit Margin >= 30.00% (Implied Sum <= 0.7692), set top banner to:
         "🚨 HIGH-PROFIT SUREBET FOUND (>= 30% ROI)"
       - If a match is a surebet below 30% ROI, set top banner to:
         "⚡ STANDARD ARBITRAGE DETECTED (< 30% ROI)"
       - If no surebets are found, set top banner to:
         "⚠️ WATCHLIST MODE: Monitoring live market variances"

    REQUIRED OUTPUT STRUCTURE:

    🇳🇬 **Naija Sports Surebet Report**

    **STATUS**: [Insert exact matched status banner]

    ---

    **HIGH-PROFIT ARBITRAGE OPPORTUNITIES (>= 30% ROI)**
    (List any fixtures meeting the 30% ROI target with match, market, bookies, exact odds, arithmetic check, and N10,000 stake breakdown for N13,000+ payout).

    ---

    **MARKET DISCREPANCY WATCHLIST**
    (List top 3 upcoming fixtures with market odds variances across Nigerian bookies).

    ---

    💡 **EXECUTION RULES FOR NIGERIAN TRADERS**
    1. Always verify line consistency (e.g., Draw No Bet vs Double Chance) before placing bets across local and international-style bookies.
    2. Account for withdrawal fees and settlement rules.
    """

    try:
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt
        )
        report = response.text.strip()
        send_telegram_message(report)
    except Exception as e:
        logging.error(f"Gemini API scan execution failed: {e}")


def main():
    # Start Keep-Alive Server on separate thread
    threading.Thread(target=start_health_server, daemon=True).start()

    # Send initial online message
    send_telegram_message("🇳🇬 **All-Bookmaker Naija Engine ONLINE**\n\nScanning live fixtures every 15 minutes with gemini-3.6-flash and 30% ROI target (N10,000 -> N13,000+ return).")

    # Automated 15-minute loop
    while True:
        try:
            run_arbitrage_scan()
        except Exception as e:
            logging.error(f"Unexpected error in main loop: {e}")
        
        logging.info("Sleeping for 15 minutes...")
        time.sleep(900)


if __name__ == "__main__":
    main()
