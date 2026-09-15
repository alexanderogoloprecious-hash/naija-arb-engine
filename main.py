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
ODDS_API_KEY = os.environ.get("ODDS_API_KEY")
PORT = int(os.environ.get("PORT", 10000))


class KeepAliveServer(BaseHTTPRequestHandler):
    """HTTP server for Render health checks and UptimeRobot keep-alive pings."""
    
    def _send_success(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()

    def do_GET(self):
        self._send_success()
        self.wfile.write(b"Naija Arb Engine is ONLINE and active.")

    def do_HEAD(self):
        self._send_success()

    def do_POST(self):
        self._send_success()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        return  # Suppress HTTP access logs in console


def start_health_server():
    server = HTTPServer(("0.0.0.0", PORT), KeepAliveServer)
    logging.info(f"Health check server listening on port {PORT}...")
    server.serve_forever()


def send_telegram_message(text):
    """Sends clean text alerts to Telegram with plain text fallback."""
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
            payload.pop("parse_mode")
            requests.post(url, json=payload, timeout=15)
        logging.info("Telegram alert delivered successfully.")
    except Exception as e:
        logging.error(f"Failed to send Telegram message: {e}")


def fetch_live_odds_context():
    """Fetches real odds data from The Odds API with DuckDuckGo fallback."""
    if ODDS_API_KEY:
        logging.info("Fetching real odds via The Odds API...")
        sports = ["soccer_epl", "soccer_spain_la_liga", "soccer_uefa_champs_league"]
        odds_summary = []

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
                if res.ok:
                    data = res.json()
                    for match in data[:3]:
                        home = match.get("home_team")
                        away = match.get("away_team")
                        start_time = match.get("commence_time")
                        
                        lines = []
                        for b in match.get("bookmakers", []):
                            for market in b.get("markets", []):
                                outcomes = [f"{o['name']}: {o['price']}" for o in market.get("outcomes", [])]
                                lines.append(f"  * {b['title']} ({market['key']}): {', '.join(outcomes)}")

                        if lines:
                            odds_summary.append(f"Match: {home} vs {away} (Starts: {start_time})\n" + "\n".join(lines[:4]))
            except Exception as e:
                logging.warning(f"Error fetching odds for {sport}: {e}")

        if odds_summary:
            return "\n\n".join(odds_summary)

    logging.info("Using DuckDuckGo context search fallback...")
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
    """Scans live odds, enforces 30% ROI minimum, and pushes structured Telegram updates with retry logic."""
    if not GEMINI_API_KEY:
        logging.error("GEMINI_API_KEY missing in environment variables.")
        return

    logging.info("Starting new odds scan cycle...")
    odds_context = fetch_live_odds_context()

    prompt = f"""
    You are an expert sports arbitrage scanner monitoring 9 Nigerian bookmakers:
    Bet9ja, SportyBet, 1xBet Nigeria, BetKing, Betway Nigeria, Betano Nigeria, MSport, 22Bet, and Melbet.

    Live Market Odds Context:
    {odds_context}

    CRITICAL RULES & TARGETS:
    1. TARGET PROFIT THRESHOLD: 30.00% MINIMUM ROI.
       - Implied Probability Sum = (1 / Odds_1) + (1 / Odds_2)
       - A 30% profit target requires Implied Probability Sum <= 0.7692 (e.g., N10,000 total bet returns N13,000+ total payout).
    2. STAKE CALCULATION MODEL (For N10,000 Total Capital):
       - Stake 1 = N10,000 / (Implied Sum * Odds_1)
       - Stake 2 = N10,000 / (Implied Sum * Odds_2)
       - Total Return must equal or exceed N13,000.
    3. FORMATTING STRICTLY FOR TELEGRAM (NO LATEX & NO MARKDOWN HEADERS):
       - NEVER use Markdown headers (#, ##, ###, ####). Use standalone bold text **LIKE THIS**.
       - NEVER use LaTeX syntax (do not use $, \\frac, or \\text). Write clean calculations like: "(1 / 1.50) + (1 / 3.00) = 0.6667 + 0.3333 = 1.0000".
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
    (List top 3 upcoming fixtures with market odds variances across bookies).

    ---

    💡 **EXECUTION RULES FOR NIGERIAN TRADERS**
    1. Always verify line consistency (e.g., Draw No Bet vs Double Chance) before placing bets across local and international-style bookies.
    2. Account for withdrawal fees and settlement rules.
    """

    # Retry loop with exponential backoff for 503 Service Unavailable errors
    max_retries = 3
    retry_delay = 10  # Seconds to wait before retrying

    for attempt in range(max_retries):
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            response = client.models.generate_content(
                model="gemini-3.6-flash",
                contents=prompt
            )
            report = response.text.strip()
            send_telegram_message(report)
            break  # Exit retry loop on successful execution
        except Exception as e:
            logging.warning(f"Gemini API attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                logging.info(f"Retrying scan in {retry_delay} seconds...")
                time.sleep(retry_delay)
                retry_delay *= 2  # Double wait time for next retry
            else:
                logging.error("All Gemini API retry attempts exhausted for this cycle.")


def main():
    # Start Keep-Alive Server on a separate thread
    threading.Thread(target=start_health_server, daemon=True).start()

    # Send initial online notification
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
