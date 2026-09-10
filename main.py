import http.server
import os
import socketserver
import threading
import time
import requests
from google import genai

# ==========================================
# 1. RENDER HEALTH CHECK SERVER
# ==========================================
PORT = int(os.environ.get("PORT", 8080))


class HealthCheckHandler(http.server.SimpleHTTPRequestHandler):

  def do_GET(self):
    self.send_response(200)
    self.send_header("Content-type", "text/plain")
    self.end_headers()
    self.wfile.write(b"Naija Arb Engine is active!")

  def do_HEAD(self):
    self.send_response(200)
    self.send_header("Content-type", "text/plain")
    self.end_headers()

  def log_message(self, format, *args):
    return  # Keep logs clean


def start_health_server():
  try:
    with socketserver.TCPServer(("", PORT), HealthCheckHandler) as httpd:
      print(f"✅ Health check server running on port {PORT}", flush=True)
      httpd.serve_forever()
  except Exception as e:
    print(f"❌ Health Server Error: {e}", flush=True)


threading.Thread(target=start_health_server, daemon=True).start()

# ==========================================
# 2. BULLETPROOF TELEGRAM NOTIFIER
# ==========================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()


def send_telegram_alert(message: str):
  if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    print(
        "⚠️ Telegram environment variables missing. Skipping alert.",
        flush=True,
    )
    return

  url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

  # Attempt 1: Send formatted message
  payload = {
      "chat_id": TELEGRAM_CHAT_ID,
      "text": message,
      "parse_mode": "Markdown",
  }

  try:
    res = requests.post(url, json=payload, timeout=10)

    # Attempt 2: If Telegram rejects special Markdown characters, fallback to plain text
    if res.status_code == 400 and "parse" in res.text.lower():
      print("⚠️ Markdown formatting error. Retrying in plain text...", flush=True)
      payload.pop("parse_mode", None)
      res = requests.post(url, json=payload, timeout=10)

    if res.status_code == 200:
      print("✅ Telegram notification delivered!", flush=True)
    else:
      print(
          f"❌ Telegram API Error ({res.status_code}): {res.text}", flush=True
      )

  except Exception as e:
    print(f"❌ Telegram Network Error: {e}", flush=True)


# Send initial startup ping
send_telegram_alert("🚀 *Naija Arb Engine is ONLINE & Scanning!*")

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
# 4. ARBITRAGE SCANNER LOOP WITH FALLBACKS
# ==========================================
PREFERRED_MODELS = ["gemini-2.5-flash", "gemini-1.5-flash"]

print("⚡ Continuous scanning engine active...", flush=True)

while True:
  print("\n🔍 Starting scan cycle...", flush=True)

  if client:
    success = False

    for model_name in PREFERRED_MODELS:
      try:
        print(f"📡 Querying model: {model_name}...", flush=True)

        response = client.models.generate_content(
            model=model_name,
            contents="Scan for active arbitrage opportunities.",
        )

        if response and hasattr(response, "text") and response.text:
          print(f"💡 Scan successful using {model_name}!", flush=True)
          scan_text = response.text

          # Deliver results to Telegram
          alert_msg = f"⚡ *Arbitrage Scan ({model_name})*\n\n{scan_text[:1000]}"
          send_telegram_alert(alert_msg)

          success = True
          break

      except Exception as e:
        print(f"⚠️ Model {model_name} failed: {e}", flush=True)

    if not success:
      print("❌ All model attempts failed during this cycle.", flush=True)
  else:
    print("⚠️ Skipping scan: Gemini client not initialized.", flush=True)

  print("⏳ Sleeping for 60 seconds...", flush=True)
  time.sleep(60)
