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
    self.wfile.write(b"Naija Arb Engine is active and healthy!")

  def do_HEAD(self):
    self.send_response(200)
    self.send_header("Content-type", "text/plain")
    self.end_headers()

  def log_message(self, format, *args):
    return  # Suppress HTTP server noise from logs


def start_health_server():
  try:
    with socketserver.TCPServer(("", PORT), HealthCheckHandler) as httpd:
      print(f"✅ Health check server listening on port {PORT}", flush=True)
      httpd.serve_forever()
  except Exception as e:
    print(f"❌ Health Check Server Error: {e}", flush=True)


# Run HTTP server in a daemon thread so it never blocks the main scanner loop
threading.Thread(target=start_health_server, daemon=True).start()

# ==========================================
# 2. TELEGRAM NOTIFIER
# ==========================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")


def send_telegram_alert(message: str):
  if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    print(
        "⚠️ Telegram environment variables missing. Skipping alert.",
        flush=True,
    )
    return

  url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
  payload = {
      "chat_id": TELEGRAM_CHAT_ID,
      "text": message,
      "parse_mode": "Markdown",
  }

  try:
    res = requests.post(url, json=payload, timeout=10)
    if res.status_code == 200:
      print("✅ Telegram notification delivered.", flush=True)
    else:
      print(
          f"⚠️ Telegram API HTTP {res.status_code}: {res.text}",
          flush=True,
      )
  except Exception as e:
    print(f"❌ Telegram Network Error: {e}", flush=True)


# Send startup message
send_telegram_alert("🚀 *Naija Arb Engine is ONLINE & Scanning!*")

# ==========================================
# 3. GEMINI API CLIENT INITIALIZATION
# ==========================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
client = None

if GEMINI_API_KEY:
  try:
    client = genai.Client(api_key=GEMINI_API_KEY)
    print("✅ Gemini API Client initialized successfully.", flush=True)
  except Exception as e:
    print(f"❌ Gemini Client Initialization Error: {e}", flush=True)
else:
  print("⚠️ GEMINI_API_KEY missing in environment variables!", flush=True)

# ==========================================
# 4. MAIN ARBITRAGE SCAN LOOP
# ==========================================
print("⚡ Engine loop initiated. Starting continuous scan...", flush=True)

while True:
  print("\n🔍 Running arbitrage scan cycle...", flush=True)

  if client:
    try:
      print("📡 Querying Gemini (gemini-2.0-flash)...", flush=True)

      response = client.models.generate_content(
          model="gemini-2.0-flash",
          contents=(
              "Identify potential arbitrage opportunities in the current"
              " market."
          ),
      )

      if response and hasattr(response, "text") and response.text:
        print("💡 Gemini Scan Result Received:", flush=True)
        print(
            f"--- [RESPONSE START] ---\n{response.text[:300]}...\n--- [RESPONSE"
            " END] ---",
            flush=True,
        )

      else:
        print("⚠️ Received empty response payload from Gemini.", flush=True)

    except Exception as e:
      print(f"❌ Gemini Execution Error: {e}", flush=True)
  else:
    print("⚠️ Skipping cycle: Gemini client not ready.", flush=True)

  print("⏳ Cycle completed. Sleeping for 60 seconds...", flush=True)
  time.sleep(60)
