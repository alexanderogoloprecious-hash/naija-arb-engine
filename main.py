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
PORT = int(os.environ.get("PORT", 10000))


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
    return  # Keep console logs clean


def start_health_server():
  try:
    with socketserver.TCPServer(("", PORT), HealthCheckHandler) as httpd:
      print(f"✅ Health check server listening on port {PORT}", flush=True)
      httpd.serve_forever()
  except Exception as e:
    print(f"❌ Health Server Error: {e}", flush=True)


threading.Thread(target=start_health_server, daemon=True).start()

# ==========================================
# 2. BULLETPROOF TELEGRAM NOTIFIER
# ==========================================
raw_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
# Automatically clean token if 'bot' prefix was accidentally included in Render
if raw_token.lower().startswith("bot"):
  TELEGRAM_BOT_TOKEN = raw_token[3:]
else:
  TELEGRAM_BOT_TOKEN = raw_token

TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()


def send_telegram_alert(message: str):
  if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    print(
        "⚠️ Telegram environment variables missing or incomplete. Skipping"
        " alert.",
        flush=True,
    )
    return

  url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

  # Primary delivery attempt with Markdown formatting
  payload = {
      "chat_id": TELEGRAM_CHAT_ID,
      "text": message,
      "parse_mode": "Markdown",
  }

  try:
    res = requests.post(url, json=payload, timeout=10)

    # Fallback delivery attempt with plain text if Markdown fails
    if res.status_code == 400 and "parse" in res.text.lower():
      print(
          "⚠️ Telegram Markdown format rejected. Retrying as plain text...",
          flush=True,
      )
      payload.pop("parse_mode", None)
      res = requests.post(url, json=payload, timeout=10)

    if res.status_code == 200:
      print("✅ Telegram alert successfully delivered!", flush=True)
    else:
      print(
          f"❌ Telegram API Error ({res.status_code}): {res.text}", flush=True
      )

  except Exception as e:
    print(f"❌ Telegram Network Error: {e}", flush=True)


# Send startup alert to verify connection
send_telegram_alert("🚀 *Naija Arb Engine Online* — System operational.")

# ==========================================
# 3. GEMINI API CLIENT INITIALIZATION
# ==========================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
client = None

if GEMINI_API_KEY:
  try:
    client = genai.Client(api_key=GEMINI_API_KEY)
    print("✅ Gemini API Client initialized successfully.", flush=True)
  except Exception as e:
    print(f"❌ Gemini Client Error: {e}", flush=True)
else:
  print("⚠️ GEMINI_API_KEY is missing in Render Environment!", flush=True)

# ==========================================
# 4. ARBITRAGE CONTINUOUS SCAN LOOP
# ==========================================
MODEL_NAME = "gemini-3.6-flash"

print(
    f"⚡ Starting main scanner loop with model {MODEL_NAME}...", flush=True
)

while True:
  print("\n🔍 Running arbitrage scan cycle...", flush=True)

  if client:
    try:
      print(f"📡 Querying {MODEL_NAME}...", flush=True)

      response = client.models.generate_content(
          model=MODEL_NAME,
          contents=(
              "Identify potential arbitrage opportunities in current markets"
              " and format as a concise alert."
          ),
      )

      if response and hasattr(response, "text") and response.text:
        print("💡 Scan successful! Sending alert to Telegram...", flush=True)
        scan_output = response.text

        alert_msg = f"⚡ *Arbitrage Scan Alert*\n\n{scan_output[:1000]}"
        send_telegram_alert(alert_msg)
      else:
        print("⚠️ Received empty response from model.", flush=True)

    except Exception as e:
      print(f"❌ Gemini Execution Error: {e}", flush=True)
  else:
    print("⚠️ Skipping cycle: Gemini client not initialized.", flush=True)

  print("⏳ Scan complete. Sleeping for 60 seconds...", flush=True)
  time.sleep(60)
