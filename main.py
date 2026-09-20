import os
import time
import logging
import threading
from datetime import datetime, timedelta, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests

try:
    from duckduckgo_search import DDGS
except ImportError:
    from ddgs import DDGS

from google import genai

# ---------------------------------------------------------------------------
# Environment Configuration & Logging Setup
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

# Quota protection: Default 1800 seconds (30 mins) to stay within free-tier limits
SCAN_INTERVAL_SECONDS = int(os.getenv("SCAN_INTERVAL_SECONDS", 1800))


# ---------------------------------------------------------------------------
# Render / UptimeRobot Keep-Alive Server
# ---------------------------------------------------------------------------
class KeepAliveServer(BaseHTTPRequestHandler):
    """Handles GET, HEAD, and POST requests for health checks and UptimeRobot pings."""
    def _send_response(self, text="OK"):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(text.encode("utf-8"))

    def do_GET(self):
        self._send_response("Naija Arb Engine is ONLINE and active.")

    def do_HEAD(self):
        self._send_response()

    def do_POST(self):
        self._send_response("OK")

    def log_message(self, format, *args):
        return  # Suppress HTTP access logs in console


def start_health_server():
    server = HTTPServer(("0.0.0.0", PORT), KeepAliveServer)
    logging.info(f"Health check server listening on port {PORT}...")
    server.serve_forever()


# ---------------------------------------------------------------------------
# Telegram Alert Dispatcher
# ---------------------------------------------------------------------------
def send_telegram_alert(text: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logging.error("Telegram credentials missing (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID)!")
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
            logging.info("Telegram alert delivered successfully.")
            return True
        else:
            # Fallback to plain text if Markdown parsing fails
            payload.pop("parse_mode", None)
            requests.post(url, json=payload, timeout=15)
            logging.info("Telegram alert delivered via plain-text fallback.")
            return True
    except Exception as e:
        logging.error(f"Failed to send Telegram message: {e}")
        return False


# ---------------------------------------------------------------------------
# Live Odds & Date Context Data Fetcher
# ---------------------------------------------------------------------------
def fetch_live_odds_context() -> str:
    now_utc = datetime.now(timezone.utc)
    today_str = now_utc.strftime("%Y-%m-%d")
    tomorrow_str = (now_utc + timedelta(days=1)).strftime("%Y-%m-%d")

    date_header = (
        f"SYSTEM CURRENT UTC TIME: {now_utc.strftime('%Y-%m-%d %H:%M UTC')}\n"
        f"STRICT TARGET MATCH DATES: TODAY ({today_str}) AND TOMORROW ({tomorrow_str})\n"
    )

    if ODDS_API_KEY:
        logging.info("Fetching real-time odds via The Odds API (Filtering Next 48 Hours)...")
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
                    for match in res.json():
                        start_raw = match.get("commence_time", "")
                        try:
                            match_dt = datetime.fromisoformat(start_raw.replace("Z", "+00:00"))
                            # Strict 48-hour window filter
                            if now_utc <= match_dt <= (now_utc + timedelta(hours=48)):
                                home = match.get("home_team")
                                away = match.get("away_team")
                                formatted_time = match_dt.strftime("%Y-%m-%d %H:%M UTC")

                                lines = []
                                for b in match.get("bookmakers", []):
                                    for m in b.get("markets", []):
                                        outcomes = [f"{o['name']}: {o['price']}" for o in m.get("outcomes", [])]
                                        lines.append(f"  * {b['title']} ({m['key']}): {', '.join(outcomes)}")

                                if lines:
                                    summary.append(
                                        f"Match: {home} vs {away}\n"
                                        f"Date & Kickoff: {formatted_time}\n" + "\n".join(lines[:4])
                                    )
                        except Exception:
                            continue
            except Exception as e:
                logging.warning(f"Error fetching Odds API data for {sport}: {e}")

        if summary:
            return f"{date_header}\n" + "\n\n".join(summary)

    logging.info("Using DuckDuckGo fallback for Today/Tomorrow match odds...")
    query = f"Nigerian bookmakers odds Bet9ja SportyBet 1xBet BetKing live matches {today_str} {tomorrow_str}"
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=8))
            snippets = [r.get("body", "") for r in results if r.get("body")]
            if snippets:
                return f"{date_header}\n" + "\n".join(snippets)
    except Exception as e:
        logging.warning(f"DuckDuckGo search fetch error: {e}")

    return f"{date_header}\nMonitoring live odds across Nigerian bookmakers for Today and Tomorrow."


# ---------------------------------------------------------------------------
# Arbitrage Scanner Engine (Gemini API Execution & Retry Logic)
# ---------------------------------------------------------------------------
def run_arbitrage_scan():
    api_keys = [k.strip() for k in GEMINI_API_KEYS_RAW.split(",") if k.strip()]
    if not api_keys:
        logging.error("No valid GEMINI_API_KEY found in environment variables.")
        return

    now_utc = datetime.now(timezone.utc)
    today_formatted = now_utc.strftime("%A, %B %d, %Y")
    tomorrow_formatted = (now_utc + timedelta(days=1)).strftime("%A, %B %d, %Y")

    odds_context = fetch_live_odds_context()

    prompt = f"""
    You are 'Naija Arb Scanner', an automated sports arbitrage scanning engine monitoring 9 Nigerian bookmakers:
    Bet9ja, SportyBet, 1xBet Nigeria, BetKing, Betway Nigeria, Betano Nigeria, MSport, 22Bet, and Melbet.

    DATE CONSTRAINTS:
    - TODAY IS: {today_formatted}
    - TOMORROW IS: {tomorrow_formatted}

    LIVE MARKET CONTEXT DATA:
    {odds_context}

    CRITICAL DATE & TIMING RULES:
    1. STRICT 48-HOUR FILTER: You MUST ONLY evaluate and report fixtures played TODAY ({today_formatted}) or TOMORROW ({tomorrow_formatted}).
    2. MANDATORY DATE DISPLAY: Every fixture reported MUST include its exact Date & Kickoff Time.
       Example: "**Date & Kickoff**: {today_formatted} @ 18:00 WAT"
    3. DISCARD OUTDATED FIXTURES: Completely ignore any past fixtures or matches beyond tomorrow.

    ARBITRAGE CALCULATIONS & ROI TARGET:
    1. MINIMUM ROI TARGET: 30.00% PROFIT.
       - Implied Sum = (1 / Odds_1) + (1 / Odds_2)
       - Profit Target requires Implied Sum <= 0.7692.
    2. STAKE CALCULATION MODEL (N10,000 Capital):
       - Stake 1 = N10,000 / (Implied Sum * Odds_1)
       - Stake 2 = N10,000 / (Implied Sum * Odds_2)
       - Total payout must reach or exceed N13,000+.
    3. STRICT FORMATTING:
       - NEVER use LaTeX syntax (do not use $, \\frac, or \\text).
       - NEVER use Markdown headers (#, ##, ###). Use standalone bold line headers **LIKE THIS**.

    STATUS BANNER LOGIC:
    - If ANY match yields Profit Margin >= 30.00%: "🚨 HIGH-PROFIT SUREBET FOUND (>= 30% ROI)"
    - If a surebet is found under 30% ROI: "⚡ STANDARD ARBITRAGE DETECTED (< 30% ROI)"
    - If no surebets are found: "⚠️ WATCHLIST MODE: Monitoring live market variances"

    REQUIRED OUTPUT STRUCTURE:

    🇳🇬 **Naija Sports Surebet Report (Today & Tomorrow)**

    **STATUS**: [Insert matched status banner]
    **SCAN DATE**: {today_formatted}

    ---

    **TODAY / TOMORROW SUREBET OPPORTUNITIES (>= 30% ROI)**
    (If found, provide Fixture Name, Date & Kickoff Time, Market, Bookies, Odds, Implied Sum calculation, and N10,000 stake breakdown).

    ---

    **IMMINENT MARKET DISCREPANCY WATCHLIST (NEXT 48 HOURS)**
    (List top 3 upcoming fixtures for TODAY or TOMORROW with market odds variances across bookies. Every listing MUST explicitly specify Date & Kickoff Time).

    Example Watchlist Format:
    1. **Enyimba vs. Rivers United (NPFL)**
    - **Date & Kickoff**: {today_formatted} @ 16:00 WAT
    - **Market**: 1X2 (Full Time)
    - **Odds Variance**: Bet9ja @ 2.10, SportyBet @ 3.85, 1xBet @ 3.40
    - **Analysis**: Implied Sum = (1 / 2.10) + (1 / 3.85) + (1 / 3.40) = 1.0300.

    ---

    💡 **EXECUTION RULES FOR NIGERIAN TRADERS**
    1. Verify market line consistency before placing bets. Odds move quickly near kickoff.
    2. Factor in withdrawal fees and settlement delays.
    """

    # Multi-Key & Model Failover Loop
    for key_idx, key in enumerate(api_keys):
        client = genai.Client(api_key=key)

        active_models = []
        try:
            for m in client.models.list():
                model_id = m.name.replace("models/", "") if hasattr(m, "name") else str(m)
                if "flash" in model_id.lower() or "pro" in model_id.lower():
                    active_models.append(model_id)
        except Exception as e:
            logging.warning(f"Model discovery failed for API Key {key_idx+1}: {e}")
            active_models = ["gemini-3.5-flash"]

        # Prioritize newest flash models
        active_models.sort(key=lambda x: ("3.6" in x or "3.5" in x), reverse=True)

        for model_name in active_models:
            max_retries = 3
            retry_delay = 10

            for attempt in range(max_retries):
                try:
                    logging.info(f"Scanning Today/Tomorrow games using {model_name} (Key {key_idx+1})...")
                    response = client.models.generate_content(
                        model=model_name,
                        contents=prompt
                    )

                    if response.text and response.text.strip():
                        send_telegram_alert(response.text.strip())
                        return
                except Exception as e:
                    err_str = str(e)
                    if "503" in err_str or "UNAVAILABLE" in err_str:
                        logging.warning(f"503 Server Busy on {model_name} (Attempt {attempt+1}/{max_retries}). Retrying in {retry_delay}s...")
                        time.sleep(retry_delay)
                        retry_delay *= 2
                    elif "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                        logging.warning(f"Quota limit hit (429) on Key {key_idx+1}. Skipping to next key/model...")
                        break
                    else:
                        logging.error(f"Execution error on {model_name}: {e}")
                        break

    logging.error("All Gemini API keys, models, and retries exhausted for this cycle.")


# ---------------------------------------------------------------------------
# Main Execution Loop
# ---------------------------------------------------------------------------
def main():
    # Start Keep-Alive Server thread for Render & UptimeRobot
    threading.Thread(target=start_health_server, daemon=True).start()

    logging.info("Naija Arb Engine started.")
    send_telegram_alert(
        "🇳🇬 **All-Bookmaker Naija Engine ONLINE**\n\n"
        "Monitoring live fixtures scheduled strictly for Today and Tomorrow with dynamic Gemini models."
    )

    while True:
        try:
            run_arbitrage_scan()
        except Exception as e:
            logging.error(f"Unexpected exception in main loop: {e}")

        logging.info(f"Scan cycle complete. Sleeping for {SCAN_INTERVAL_SECONDS} seconds...")
        time.sleep(SCAN_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
