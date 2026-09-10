import http.server
import os
import threading
import time
import requests
from google import genai
from google.genai import types

# ==========================================
# 1. IMMEDIATE WEB PORT BINDING (RENDER HEALTH CHECK)
# ==========================================
PORT = int(os.environ.get("PORT", 10000))

class HealthCheckHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK - Ultra-Precision Naija Arb Engine Active")

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()

    def log_message(self, format, *args):
        return  # Suppress health check logs from stdout

def run_web_server():
    try:
        server_address = ("0.0.0.0", PORT)
        httpd = http.server.ThreadingHTTPServer(server_address, HealthCheckHandler)
        print(f"✅ Web Port Server bound to 0.0.0.0:{PORT}", flush=True)
        httpd.serve_forever()
    except Exception as e:
        print(f"❌ Web Port Server Error: {e}", flush=True)

server_thread = threading.Thread(target=run_web_server, daemon=True)
server_thread.start()
time.sleep(1)

# ==========================================
# 2. BULLETPROOF TELEGRAM NOTIFIER
# ==========================================
raw_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_BOT_TOKEN = raw_token[3:] if raw_token.lower().startswith("bot") else raw_token
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

def send_telegram_alert(message: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Missing Telegram environment variables.", flush=True)
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
    }

    try:
        res = requests.post(url, json=payload, timeout=12)
        if res.status_code == 400 and "parse" in res.text.lower():
            payload.pop("parse_mode", None)
            res = requests.post(url, json=payload, timeout=12)

        if res.status_code == 200:
            print("✅ Telegram alert delivered successfully!", flush=True)
        else:
            print(f"❌ Telegram API Error ({res.status_code}): {res.text}", flush=True)
    except Exception as e:
        print(f"❌ Telegram Connection Error: {e}", flush=True)

send_telegram_alert("🇳🇬 *Ultra-Precision Naija Sports Surebet Engine ONLINE*\n\nRunning scans across Nigerian bookmakers...")

# ==========================================
# 3. GEMINI API CLIENT INITIALIZATION
# ==========================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
client = None

if GEMINI_API_KEY:
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        print("✅ Gemini API Client initialized.", flush=True)
    except Exception as e:
        print(f"❌ Gemini Initialization Error: {e}", flush=True)
else:
    print("⚠️ GEMINI_API_KEY missing in environment variables!", flush=True)

# ==========================================
# 4. EXCLUSIVE NIGERIAN SPORTS SUREBET PROMPT
# ==========================================
MODEL_NAME = "gemini-3.8-flash"

NIGERIAN_SPORTS_SUREBET_PROMPT = """
You are an elite quantitative sports arbitrage (surebet) analyst focused exclusively on NIGERIAN SPORTSBOOKS.

Search and analyze live or upcoming sports events across these licensed Nigerian bookmakers:
- SportyBet Nigeria
- Bet9ja
- BetKing
- 1xBet Nigeria
- Betway Nigeria
- MSport
- Betano Nigeria
- 22Bet Nigeria
- Melbet Nigeria

CORE OBJECTIVES & STRICT ARBITRAGE RULES:
1. TARGET HIGH-DISCREPANCY MARKETS: Focus on Football (1X2, Over/Under 2.5/3.5, Both Teams to Score, Double Chance), Basketball (Moneyline, Handiaps), and Tennis (Match Winner).
2. MATHEMATICAL SUREBET VERIFICATION:
   - For 2-Way Markets: (1 / Odds1) + (1 / Odds2) MUST be LESS THAN 1.00.
   - For 3-Way Markets: (1 / Odds1) + (1 / Odds2) + (1 / Odds3) MUST be LESS THAN 1.00.
   - Calculate exact profit percentage: Profit % = ((1 / Sum of Implied Probabilities) - 1) * 100.
3. ZERO NON-NIGERIAN OR NON-SPORTS NOISE: Do NOT mention crypto, forex, stocks, or international non-Nigerian sportsbooks.
4. BUDGET STAKE CALCULATOR: All stake allocations MUST be calculated using an exact total budget of ₦10,000 Naira.

FORMAT THE TELEGRAM OUTPUT EXACTLY AS FOLLOWS:

🔥 **HIGH-YIELD NAIJA SUREBET DETECTED**
----------------------------------
📌 **Event**: [Sport / League] — [Team A vs Team B]
⏰ **Kickoff**: [Match Time & Date]
🎯 **Betting Market**: [e.g., Over/Under 2.5 Goals / Match Winner 1X2]

📊 **VERIFIED ODDS & BOOKMAKERS**:
- **Selection 1**: [Option 1] @ **[Odds]** on **[Nigerian Bookmaker 1]**
- **Selection 2**: [Option 2] @ **[Odds]** on **[Nigerian Bookmaker 2]**
- (Selection 3 if 3-way market) @ **[Odds]** on **[Nigerian Bookmaker 3]**

📈 **GUARANTEED PROFIT MARGIN**: **[X.XX]%**

💰 **OPTIMAL STAKE ALLOCATION (₦10,000 Budget)**:
- **Stake ₦[Amount]** on [Selection 1] @ [Bookmaker 1] ➔ Potential Payout: ₦[Return]
- **Stake ₦[Amount]** on [Selection 2] @ [Bookmaker 2] ➔ Potential Payout: ₦[Return]
- **Guaranteed Net Profit**: ₦[Profit]

----------------------------------
If no 100% mathematically confirmed surebet is live in this scan cycle, provide a "High-Odds Discrepancy Watchlist" highlighting top matches currently close to arbitrage across SportyBet, Bet9ja, and BetKing.
"""

search_config = types.GenerateContentConfig(
    tools=[types.Tool(google_search=types.GoogleSearch())]
)

# ==========================================
# 5. CONTINUOUS SCANNER LOOP WITH BACKOFF
# ==========================================
SCAN_INTERVAL_SECONDS = 300  # 5-minute scans for maximum stability
print(f"⚡ Ultra-precision scanner active using {MODEL_NAME}...", flush=True)

while True:
    print("\n🇳🇬 Scanning Nigerian sportsbooks for high-margin surebets...", flush=True)

    if client:
        try:
            print(f"📡 Querying Gemini ({MODEL_NAME}) with Search Grounding...", flush=True)

            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=NIGERIAN_SPORTS_SUREBET_PROMPT,
                config=search_config
            )

            if response and hasattr(response, "text") and response.text:
                print("💡 High-yield scan complete! Sending Telegram alert...", flush=True)
                alert_msg = f"⚽ *Naija Sports Surebet Alert*\n\n{response.text[:3500]}"
                send_telegram_alert(alert_msg)
            else:
                print("⚠️ Received empty response payload from Gemini.", flush=True)

        except Exception as e:
            err_msg = str(e)
            print(f"❌ Gemini Execution Error: {err_msg}", flush=True)

            if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                print("⏳ Rate limit reached. Pausing for 10 minutes to reset quota...", flush=True)
                time.sleep(600)
                continue
    else:
        print("⚠️ Skipping cycle: Gemini client not ready.", flush=True)

    print(f"⏳ Waiting {SCAN_INTERVAL_SECONDS} seconds for next scan...", flush=True)
    time.sleep(SCAN_INTERVAL_SECONDS)
