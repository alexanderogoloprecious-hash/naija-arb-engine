import http.server
import os
import threading
import time
import requests
from google import genai
from google.genai import types

# ==========================================
# 1. IMMEDIATE WEB PORT BINDING (RENDER REQUIRED)
# ==========================================
PORT = int(os.environ.get("PORT", 10000))


class HealthCheckHandler(http.server.BaseHTTPRequestHandler):

  def do_GET(self):
    self.send_response(200)
    self.send_header("Content-type", "text/plain")
    self.end_headers()
    self.wfile.write(b"OK - Naija Sports Arb Engine Active")

  def do_HEAD(self):
    self.send_response(200)
    self.send_header("Content-type", "text/plain")
    self.end_headers()

  def log_message(self, format, *args):
    return  # Suppress HTTP server stdout logs


def run_web_server():
  try:
    server_address = ("0.0.0.0", PORT)
    httpd = http.server.ThreadingHTTPServer(server_address, HealthCheckHandler)
    print(f"✅ Web Port Server bound to 0.0.0.0:{PORT}", flush=True)
    httpd.serve_forever()
  except Exception as e:
    print(f"❌ Web Port Server Error: {e}", flush=True)


# Fire up web port server immediately in a background daemon thread
server_thread = threading.Thread(target=run_web_server, daemon=True)
server_thread.start()
time.sleep(1)

# ==========================================
# 2. BULLETPROOF TELEGRAM NOTIFIER
# ==========================================
raw_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
if raw_token.lower().startswith("bot"):
  TELEGRAM_BOT_TOKEN = raw_token[3:]
else:
  TELEGRAM_BOT_TOKEN = raw_token

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

    # Markdown fallback mechanism
    if res.status_code == 400 and "parse" in res.text.lower():
      print("⚠️ Retrying Telegram message in plain text...", flush=True)
      payload.pop("parse_mode", None)
      res = requests.post(url, json=payload, timeout=12)

    if res.status_code == 200:
      print("✅ Telegram alert delivered successfully!", flush=True)
    else:
      print(
          f"❌ Telegram API Error ({res.status_code}): {res.text}", flush=True
      )

  except Exception as e:
    print(f"❌ Telegram Connection Error: {e}", flush=True)


send_telegram_alert(
    "🇳🇬 *Naija Sports Surebet Engine ONLINE*\n\nMonitoring Nigerian"
    " Bookmakers for sports arbitrage..."
)

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
# 4. EXCLUSIVE NIGERIAN SPORTS PROMPT & CONFIG
# ==========================================
MODEL_NAME = "gemini-3.6-flash"

NIGERIAN_SPORTS_SUREBET_PROMPT = """
You are a dedicated Sports Betting Arbitrage (Surebet) Scanner focused exclusively on NIGERIAN BOOKMAKERS.

Search for live/upcoming sports matches across top licensed sportsbooks in Nigeria:
- SportyBet Nigeria
- Bet9ja
- BetKing
- 1xBet Nigeria
- Betway Nigeria
- MSport
- Betano Nigeria
- 22Bet Nigeria
- Melbet Nigeria

CRITICAL RULES:
1. STRICTLY analyze sports matches (Football, Basketball, Tennis, Boxing, MMA, Table Tennis).
2. ONLY compare odds between NIGERIAN sportsbooks listed above. Do NOT include crypto, forex, or non-Nigerian platforms.
3. Identify 2-way or 3-way sports arbitrage opportunities where odds across bookmakers guarantee a profit.

FORMAT THE TELEGRAM OUTPUT EXACTLY AS FOLLOWS:

⚽ **NIGERIAN SPORTS SUREBET**
----------------------------------
📌 **Event**: [League / Sport] — [Team A vs Team B]
⏰ **Match Time**: [Time/Date]
🎯 **Bet Market**: [e.g., Match Winner 1X2 / Over 2.5 Goals / Both Teams to Score]

📊 **ODDS COMPARISON**:
- **Selection 1**: [Option 1] @ **[Odds]** on **[Nigerian Bookmaker 1]**
- **Selection 2**: [Option 2] @ **[Odds]** on **[Nigerian Bookmaker 2]**
- (If 3-way market, add Selection 3 @ [Odds] on [Nigerian Bookmaker 3])

📈 **PROFIT MARGIN**: **[X.XX]%**

💰 **STAKE ALLOCATION EXAMPLE (₦10,000 Total Stake)**:
- Stake ₦[Amount] on [Bookmaker 1] -> Potential Return: ₦[Payout]
- Stake ₦[Amount] on [Bookmaker 2] -> Potential Return: ₦[Payout]
- **Guaranteed Net Profit**: ₦[Profit]

----------------------------------
If no 100% guaranteed surebet exists in this cycle, provide a summary of top high-odds sports matches currently monitored across SportyBet, Bet9ja, and BetKing.
"""

search_config = types.GenerateContentConfig(
    tools=[types.Tool(google_search=types.GoogleSearch())]
)

# ==========================================
# 5. CONTINUOUS ARBITRAGE SCAN LOOP
# ==========================================
print(f"⚡ Continuous sports scanner active using {MODEL_NAME}...", flush=True)

while True:
  print("\n🇳🇬 Running Nigerian sports surebet scan...", flush=True)

  if client:
    try:
      print(
          f"📡 Querying Gemini ({MODEL_NAME}) with Search Grounding...",
          flush=True,
      )

      response = client.models.generate_content(
          model=MODEL_NAME,
          contents=NIGERIAN_SPORTS_SUREBET_PROMPT,
          config=search_config,
      )

      if response and hasattr(response, "text") and response.text:
        print("💡 Sports scan complete! Sending alert...", flush=True)
        scan_output = response.text

        alert_msg = f"⚽ *Naija Sports Surebet*\n\n{scan_output[:3500]}"
        send_telegram_alert(alert_msg)
      else:
        print("⚠️ Received empty response payload from Gemini.", flush=True)

    except Exception as e:
      print(f"❌ Gemini Execution Error: {e}", flush=True)
  else:
    print("⚠️ Skipping cycle: Gemini client not ready.", flush=True)

  print("⏳ Waiting 60 seconds for next cycle...", flush=True)
  time.sleep(60)
