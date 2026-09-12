import http.server
import os
import threading
import time
import requests
from google import genai
from duckduckgo_search import DDGS

# ==========================================
# 1. RENDER PORT BINDING (HEALTH CHECK)
# ==========================================
PORT = int(os.environ.get("PORT", 10000))

class HealthCheckHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK - Free Search Naija Arb Engine Online")

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()

    def log_message(self, format, *args):
        return

def start_health_server():
    try:
        server_address = ("0.0.0.0", PORT)
        httpd = http.server.ThreadingHTTPServer(server_address, HealthCheckHandler)
        print(f"✅ Render Web Port Listener active on 0.0.0.0:{PORT}", flush=True)
        httpd.serve_forever()
    except Exception as e:
        print(f"❌ Web Port Error: {e}", flush=True)

threading.Thread(target=start_health_server, daemon=True).start()
time.sleep(1)

# ==========================================
# 2. TELEGRAM ALERT SYSTEM
# ==========================================
raw_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_BOT_TOKEN = raw_token[3:] if raw_token.lower().startswith("bot") else raw_token
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

def send_telegram_alert(message: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Missing Telegram credentials.", flush=True)
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
            print("✅ Telegram alert delivered!", flush=True)
        else:
            print(f"❌ Telegram Error ({res.status_code}): {res.text}", flush=True)
    except Exception as e:
        print(f"❌ Telegram Connection Error: {e}", flush=True)

# ==========================================
# 3. FREE DUCKDUCKGO WEB SEARCH
# ==========================================
def fetch_live_sports_data():
    queries = [
        "SportyBet Nigeria live match odds today",
        "Bet9ja football odds today",
        "BetKing match odds Nigeria"
    ]
    search_results = []
    
    try:
        with DDGS() as ddgs:
            for q in queries:
                results = list(ddgs.text(q, max_results=3))
                for r in results:
                    search_results.append(f"Title: {r.get('title')}\nSnippet: {r.get('body')}")
        return "\n\n".join(search_results)
    except Exception as e:
        print(f"⚠️ Search error: {e}", flush=True)
        return "No external web search results available."

# ==========================================
# 4. GEMINI ANALYSIS & PROMPT
# ==========================================
api_key = os.environ.get("GEMINI_API_KEY", "").strip()
client = genai.Client(api_key=api_key) if api_key else None

MODEL_NAME = "gemini-2.5-flash"

SYSTEM_PROMPT = """
You are an expert quantitative sports arbitrage analyst specializing in NIGERIAN BOOKMAKERS (SportyBet, Bet9ja, BetKing, 1xBet Nigeria, Betway Nigeria, MSport).

Analyze the provided web search context and search for live/upcoming sports surebets.

STRICT ARBITRAGE RULES:
1. 2-Way Markets: (1/Odds1) + (1/Odds2) MUST be LESS THAN 1.00.
2. 3-Way Markets: (1/Odds1) + (1/Odds2) + (1/Odds3) MUST be LESS THAN 1.00.
3. Profit Margin % = ((1 / Sum of Implied Probabilities) - 1) * 100.
4. Calculate stake distribution for a TOTAL BUDGET OF ₦10,000 NAIRA.

FORMAT OUTPUT EXACTLY AS:

🔥 **HIGH-YIELD NAIJA SUREBET DETECTED**
----------------------------------
📌 **Event**: [Sport / League] — [Team A vs Team B]
⏰ **Kickoff**: [Match Date & Time]
🎯 **Market**: [Over/Under 2.5 / 1X2]

📊 **VERIFIED ODDS & BOOKMAKERS**:
- **Selection 1**: [Option 1] @ **[Odds]** on **[Bookmaker 1]**
- **Selection 2**: [Option 2] @ **[Bookmaker 2]**

📈 **GUARANTEED PROFIT MARGIN**: **[X.XX]%**

💰 **STAKE ALLOCATION (₦10,000 BUDGET)**:
- **Stake ₦[Amount]** on [Selection 1] @ [Bookmaker 1] ➔ Expected Return: ₦[Return]
- **Stake ₦[Amount]** on [Selection 2] @ [Bookmaker 2] ➔ Expected Return: ₦[Return]
- **Net Guaranteed Profit**: ₦[Profit]

----------------------------------
If no 100% mathematically confirmed surebet exists in this data, provide a short "High-Odds Discrepancy Watchlist" across SportyBet, Bet9ja, and BetKing.
"""

send_telegram_alert("🇳🇬 *Free-Tier Naija Sports Engine ONLINE*\n\nRunning 15-minute search cycles without API billing requirements.")

# ==========================================
# 5. CONTINUOUS SCANNER LOOP
# ==========================================
SCAN_INTERVAL_SECONDS = 900  # 15 minutes

while True:
    print("\n🇳🇬 Gathering live Nigerian sports data via free search...", flush=True)
    live_data = fetch_live_sports_data()

    if client:
        try:
            print(f"📡 Analyzing odds with Gemini ({MODEL_NAME})...", flush=True)
            user_content = f"LIVE SEARCH DATA:\n{live_data}\n\n{SYSTEM_PROMPT}"
            
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=user_content
            )

            if response and hasattr(response, "text") and response.text:
                print("💡 Analysis complete! Sending Telegram alert...", flush=True)
                send_telegram_alert(f"⚽ *Naija Sports Surebet Alert*\n\n{response.text[:3500]}")
            else:
                print("⚠️ Empty response from Gemini.", flush=True)

        except Exception as e:
            print(f"❌ Gemini Execution Error: {e}", flush=True)

    print(f"⏳ Waiting {SCAN_INTERVAL_SECONDS // 60} minutes for next cycle...", flush=True)
    time.sleep(SCAN_INTERVAL_SECONDS)
