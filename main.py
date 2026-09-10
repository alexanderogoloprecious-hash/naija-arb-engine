import http.server
import os
import threading
import time
import requests
from google import genai
from google.genai import types

# ==========================================
# 1. RENDER PORT BINDING (HEALTH CHECK)
# ==========================================
PORT = int(os.environ.get("PORT", 10000))


class HealthCheckHandler(http.server.BaseHTTPRequestHandler):

  def do_GET(self):
    self.send_response(200)
    self.send_header("Content-type", "text/plain")
    self.end_headers()
    self.wfile.write(b"OK - Multi-Key Naija Arb Engine Online")

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
    print(
        f"✅ Render Web Port Listener active on 0.0.0.0:{PORT}", flush=True
    )
    httpd.serve_forever()
  except Exception as e:
    print(f"❌ Web Port Error: {e}", flush=True)


threading.Thread(target=start_health_server, daemon=True).start()
time.sleep(1)

# ==========================================
# 2. TELEGRAM ALERT SYSTEM
# ==========================================
raw_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_BOT_TOKEN = (
    raw_token[3:] if raw_token.lower().startswith("bot") else raw_token
)
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()


def send_telegram_alert(message: str):
  if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    print("⚠️ Missing Telegram credentials in Environment.", flush=True)
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
      print(
          f"❌ Telegram API Error ({res.status_code}): {res.text}", flush=True
      )
  except Exception as e:
    print(f"❌ Telegram Connection Error: {e}", flush=True)


# ==========================================
# 3. SMART MULTI-KEY ROTATION SYSTEM
# ==========================================
class GeminiKeyManager:

  def __init__(self):
    raw_keys = [
        os.environ.get("GEMINI_API_KEY", "").strip(),
        os.environ.get("GEMINI_API_KEY_2", "").strip(),
        os.environ.get("GEMINI_API_KEY_3", "").strip(),
    ]
    self.keys = [k for k in raw_keys if k]
    self.cooldowns = {i: 0 for i in range(len(self.keys))}
    self.current_index = 0

    if not self.keys:
      print("❌ CRITICAL: No valid Gemini API keys detected!", flush=True)
    else:
      print(
          f"🔑 Initialized multi-key system with {len(self.keys)} active API"
          " key(s).",
          flush=True,
      )

  def get_active_client(self):
    now = time.time()
    num_keys = len(self.keys)

    if num_keys == 0:
      return None, None

    for offset in range(num_keys):
      idx = (self.current_index + offset) % num_keys
      if now >= self.cooldowns[idx]:
        self.current_index = idx
        key = self.keys[idx]
        try:
          client = genai.Client(api_key=key)
          return client, idx + 1
        except Exception as e:
          print(f"❌ Failed to build client for Key #{idx + 1}: {e}", flush=True)

    earliest_reset = min(self.cooldowns.values())
    wait_time = max(10, int(earliest_reset - now))
    print(
        f"⏳ All {num_keys} API keys are rate-limited. Sleeping for"
        f" {wait_time}s until reset...",
        flush=True,
    )
    time.sleep(wait_time)
    return self.get_active_client()

  def mark_key_exhausted(self, key_num: int, cooldown_seconds: int = 600):
    idx = key_num - 1
    self.cooldowns[idx] = time.time() + cooldown_seconds
    print(
        f"⚠️ Key #{key_num} rate-limited (429). Put on cooldown for"
        f" {cooldown_seconds // 60} minutes.",
        flush=True,
    )
    self.current_index = (self.current_index + 1) % len(self.keys)


key_manager = GeminiKeyManager()

# ==========================================
# 4. HIGH-ACCURACY NIGERIAN SUREBET PROMPT
# ==========================================
MODEL_NAME = "gemini-3.6-flash"

NIGERIAN_SPORTS_SUREBET_PROMPT = """
You are an expert quantitative sports arbitrage analyst specializing exclusively in NIGERIAN BOOKMAKERS.

Scour live and upcoming sports matches across licensed sportsbooks in Nigeria:
- SportyBet Nigeria
- Bet9ja
- BetKing
- 1xBet Nigeria
- Betway Nigeria
- MSport
- Betano Nigeria
- 22Bet Nigeria
- Melbet Nigeria

STRICT RULES & MATHEMATICAL VALIDATION:
1. ARBITRAGE FORMULA VALIDATION:
   - 2-Way Markets: (1 / Odds1) + (1 / Odds2) MUST be strictly LESS THAN 1.00.
   - 3-Way Markets: (1 / Odds1) + (1 / Odds2) + (1 / Odds3) MUST be strictly LESS THAN 1.00.
   - Profit Margin % = ((1 / Sum of Implied Probabilities) - 1) * 100.
2. HIGH-DISCREPANCY MARKETS: Prioritize Football (1X2, Over/Under 2.5/3.5, BTTS), Basketball (Moneyline, Spread), and Tennis.
3. BUDGET STAKE ALLOCATION: Calculate exact stake distribution for a TOTAL BUDGET OF ₦10,000 NAIRA.
4. NIGERIAN CONTEXT ONLY: Do NOT include foreign non-Nigerian bookies, crypto, forex, or non-sports markets.

FORMAT TELEGRAM OUTPUT EXACTLY AS:

🔥 **HIGH-YIELD NAIJA SUREBET DETECTED**
----------------------------------
📌 **Event**: [Sport / League] — [Team A vs Team B]
⏰ **Kickoff**: [Match Date & Time]
🎯 **Market**: [e.g., Over/Under 2.5 Goals / Match Winner 1X2]

📊 **VERIFIED ODDS & BOOKMAKERS**:
- **Selection 1**: [Option 1] @ **[Odds]** on **[Nigerian Bookmaker 1]**
- **Selection 2**: [Option 2] @ **[Odds]** on **[Nigerian Bookmaker 2]**
- (Selection 3 if 3-way) @ **[Odds]** on **[Nigerian Bookmaker 3]**

📈 **GUARANTEED PROFIT MARGIN**: **[X.XX]%**

💰 **STAKE ALLOCATION (₦10,000 TOTAL BUDGET)**:
- **Stake ₦[Amount]** on [Selection 1] @ [Bookmaker 1] ➔ Expected Return: ₦[Return]
- **Stake ₦[Amount]** on [Selection 2] @ [Bookmaker 2] ➔ Expected Return: ₦[Return]
- **Net Guaranteed Profit**: ₦[Profit]

----------------------------------
If no 100% mathematically confirmed surebet exists in this current cycle, output a concise "High-Odds Discrepancy Watchlist" highlighting top matches currently monitored across SportyBet, Bet9ja, and BetKing.
"""

search_config = types.GenerateContentConfig(
    tools=[types.Tool(google_search=types.GoogleSearch())]
)

send_telegram_alert(
    "🇳🇬 *Multi-Key Naija Sports Engine ONLINE*\n\nEngine active using"
    " gemini-3.6-flash with 3-key automated failover & ₦10,000 stake calculator."
)

# ==========================================
# 5. CONTINUOUS SCANNER LOOP WITH ROTATION
# ==========================================
SCAN_INTERVAL_SECONDS = 300  # 5-minute scans

while True:
  print("\n🇳🇬 Starting Nigerian sports surebet scan cycle...", flush=True)

  client, key_num = key_manager.get_active_client()

  if client:
    try:
      print(
          f"📡 Querying Gemini ({MODEL_NAME}) using Key #{key_num}...",
          flush=True,
      )

      response = client.models.generate_content(
          model=MODEL_NAME,
          contents=NIGERIAN_SPORTS_SUREBET_PROMPT,
          config=search_config,
      )

      if response and hasattr(response, "text") and response.text:
        print(
            f"💡 Scan completed successfully using Key #{key_num}! Sending"
            " alert...",
            flush=True,
        )
        alert_msg = f"⚽ *Naija Sports Surebet Alert*\n\n{response.text[:3500]}"
        send_telegram_alert(alert_msg)
      else:
        print("⚠️ Empty response received from Gemini.", flush=True)

    except Exception as e:
      err_str = str(e)
      print(
          f"❌ Gemini Execution Error on Key #{key_num}: {err_str}", flush=True
      )

      if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
        key_manager.mark_key_exhausted(key_num, cooldown_seconds=600)
        continue
  else:
    print("⚠️ Engine waiting for active API key...", flush=True)

  print(
      f"⏳ Waiting {SCAN_INTERVAL_SECONDS} seconds for next scan cycle...",
      flush=True,
  )
  time.sleep(SCAN_INTERVAL_SECONDS)
