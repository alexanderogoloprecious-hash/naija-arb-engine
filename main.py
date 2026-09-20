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

# Supports multiple comma-separated keys for automatic failover: "KEY1,KEY2"
GEMINI_API_KEYS_RAW = os.getenv("GEMINI_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
ODDS_API_KEY = os.getenv("ODDS_API_KEY")
PORT = int(os.getenv("PORT", 10000))


# ---------------------------------------------------------------------------
# Health Check Server
# ---------------------------------------------------------------------------
class KeepAliveServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Naija Arb Engine is active.")

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()

    def log_message(self, format, *args):
        return


def start_health_server():
    server = HTTPServer(("0.0.0.0", PORT), KeepAliveServer)
    logging.info(f"Keep-alive HTTP server running on port {PORT}...")
    server.serve_forever()


# ---------------------------------------------------------------------------
# Telegram Dispatcher
# ---------------------------------------------------------------------------
def send_telegram_alert(text: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logging.error("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing.")
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
        if res.status_code == 200:
            logging.info("Telegram alert sent successfully.")
            return True
        else:
            payload.pop("parse_mode", None)
            requests.post(url, json=payload, timeout=15)
            logging.info("Telegram alert delivered via plain text fallback.")
            return True
    except Exception as e:
        logging.error(f"Telegram notification error: {e}")
        return False


# ---------------------------------------------------------------------------
# Market Context Fetcher
# ---------------------------------------------------------------------------
def fetch_live_odds_context() -> str:
    if ODDS_API_KEY:
        logging.info("Fetching structured odds via The Odds API...")
        sports = ["soccer_epl", "soccer_spain_la_liga", "soccer_uefa_champs_league"]
        summary = []
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
                    for match in res.json()[:3]:
                        home = match.get("home_team")
                        away = match.get("away_team")
                        start = match.get("commence_time")
                        lines = []
                        for b in match.get("bookmakers", []):
                            for m in b.get("markets", []):
                                outcomes = [f"{o['name']}: {o['price']}" for o in m.get("outcomes", [])]
                                lines.append(f"  * {b['title']} ({m['key']}): {', '.join(outcomes)}")
                        if lines:
                            summary.append(f"Match: {home} vs {away} (Start: {start})\n" + "\n".join(lines[:4]))
            except Exception as e:
                logging.warning(f"The Odds API error for {sport}: {e}")

        if summary:
            return "\n\n".join(summary)

    logging.info("Fetching context via DuckDuckGo fallback...")
    query = "Nigerian bookmakers odds Bet9ja SportyBet 1xBet BetKing Betway Betano MSport live football matches today"
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=8))
            snippets = [r.get("body", "") for r in results if r.get("body")]
            if snippets:
                return "\n".join(snippets)
    except Exception as e:
        logging.warning(f"DuckDuckGo search error: {e}")

    return "Standard odds monitoring active across Nigerian bookmakers."


# ---------------------------------------------------------------------------
# Dynamic Model Discovery & Execution
# ---------------------------------------------------------------------------
def run_arbitrage_scan():
    api_keys = [k.strip() for k in GEMINI_API_KEYS_RAW.split(",") if k.strip()]
    if not api_keys:
        logging.error("No valid GEMINI_API_KEY configured.")
        return

    odds_context = fetch_live_odds_context()

    prompt = f"""
    You are 'Naija Arb Scanner', an automated sports arbitrage monitoring system tracking 9 Nigerian bookmakers:
    Bet9ja, SportyBet, 1xBet, BetKing, Betway, Betano, MSport, 22Bet, and Melbet.

    LIVE MARKET CONTEXT DATA:
    {odds_context}

    CRITICAL RULES & CALCULATIONS:
    1. PROFIT TARGET: 30.00% MINIMUM ROI.
       - Implied Probability Sum = (1 / Odds_1) + (1 / Odds_2)
       - A 30% profit requires Implied Probability Sum <= 0.7692 (e.g., N10,000 capital returns N13,000+ total payout).
    2. STAKE CALCULATION MODEL (N10,000 Total Capital):
       - Stake 1 = N10,000 / (Implied Sum * Odds_1)
       - Stake 2 = N10,000 / (Implied Sum * Odds_2)
    3. FORMATTING (NO LATEX & NO MARKDOWN HEADERS):
       - DO NOT use Markdown headers (#, ##, ###). Use standalone bold line tags **LIKE THIS**.
       - DO NOT use LaTeX syntax. Write standard math like: "(1 / 1.50) + (1 / 3.00) = 0.6667 + 0.3333 = 1.0000".
    4. STATUS BANNER RULE:
       - If any match yields Profit Margin >= 30.00% (Implied Sum <= 0.7692): set banner to "🚨 HIGH-PROFIT SUREBET FOUND (>= 30% ROI)"
       - If a surebet is found below 30% ROI: set banner to "⚡ STANDARD ARBITRAGE DETECTED (< 30% ROI)"
       - If no surebets are found: set banner to "⚠️ WATCHLIST MODE: Monitoring live market variances"

    REQUIRED OUTPUT FORMAT:

    🇳🇬 **Naija Sports Surebet Report**

    **STATUS**: [Insert exact matched status banner]

    ---

    **HIGH-PROFIT ARBITRAGE OPPORTUNITIES (>= 30% ROI)**
    (List fixture, market, operators, odds, calculation, and N10,000 stake breakdown).

    ---

    **MARKET DISCREPANCY WATCHLIST**
    (Top 3 upcoming matches with odds variance across operators).

    ---

    💡 **EXECUTION RULES FOR NIGERIAN TRADERS**
    1. Verify market line consistency before placing bets.
    2. Factor in withdrawal fees and settlement delays.
    """

    for key_idx, key in enumerate(api_keys):
        client = genai.Client(api_key=key)

        # Discover active models available on this API key dynamically
        active_models = []
        try:
            for m in client.models.list():
                model_id = m.name.replace("models/", "") if hasattr(m, "name") else str(m)
                if "flash" in model_id.lower() or "pro" in model_id.lower():
                    active_models.append(model_id)
        except Exception as e:
            logging.warning(f"Could not fetch model list dynamically for Key {key_idx+1}: {e}")
            active_models = ["gemini-3.6-flash"]

        # Prioritize 3.6/3.5 models
        active_models.sort(key=lambda x: ("3.6" in x or "3.5" in x), reverse=True)

        for model_name in active_models:
            try:
                logging.info(f"Scanning with {model_name} (API Key {key_idx+1})...")
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt
                )

                if response.text and response.text.strip():
                    send_telegram_alert(response.text.strip())
                    return
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    logging.warning(f"Quota limit reached for {model_name} on Key {key_idx+1} (429). Trying next...")
                elif "404" in err_str or "NOT_FOUND" in err_str:
                    logging.warning(f"Model {model_name} unavailable (404). Skipping...")
                else:
                    logging.error(f"Execution error on {model_name}: {e}")

    logging.error("All Gemini API keys and active models exhausted for this cycle.")


# ---------------------------------------------------------------------------
# Main Execution Loop
# ---------------------------------------------------------------------------
def main():
    threading.Thread(target=start_health_server, daemon=True).start()
    logging.info("Naija Arb Engine started.")
    send_telegram_alert("🇳🇬 **Naija Arb Engine Online**\n\nAutomated scanning active across Nigerian operators.")

    while True:
        try:
            run_arbitrage_scan()
        except Exception as e:
            logging.error(f"Unexpected loop exception: {e}")

        logging.info("Cycle complete. Sleeping for 15 minutes...")
        time.sleep(900)


if __name__ == "__main__":
    main()
