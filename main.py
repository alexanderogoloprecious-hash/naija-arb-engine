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
    return  # Silence server logs to keep console clean


def start_health_server():
  with socketserver.TCPServer(("", PORT), HealthCheckHandler) as httpd:
    print(f"Health check server running on port {PORT}", flush=True)
    httpd.serve_forever()


# Run HTTP health check server on a background thread for Render
threading.Thread(target=start_health_server, daemon=True).start()

# ==========================================
# 2. TELEGRAM NOTIFICATION HELPER
# ==========================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")


def send_telegram_alert(message):
  if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    print(
        "⚠️ Telegram credentials missing. Skipping notification.", flush=True
    )
    return

  url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
  try:
    response = requests.post(
        url,
        json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown",
        },
        timeout=10,
    )
    if response.status_code == 200:
      print("✅ Telegram notification sent successfully!", flush=True)
    else:
      print(
          f"⚠️ Telegram API response error: {response.status_code} -"
          f" {response.text}",
          flush=True,
      )
  except Exception as e:
    print(f"❌ Failed to send Telegram alert: {e}", flush=True)


# Send immediate startup notification
send_telegram_alert("🚀 *Naija Arb Engine is ONLINE & scanning!*")

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
    print(f"❌ Gemini Initialization Error: {e}", flush=True)
else:
  print("⚠️ GEMINI_API_KEY missing in Environment Variables!", flush=True)

# ==========================================
# 4. MAIN ARBITRAGE SCANNING LOOP
# ==========================================
print("⚡ Starting main arbitrage engine loop...", flush=True)

while True:
  print("🔍 Starting scan cycle...", flush=True)

  if client:
    try:
      print("📡 Fetching scan data via Gemini...", flush=True)

      response = client.models.generate_content(
          model="gemini-2.5-flash",
          contents="Scan for active arbitrage opportunities.",
      )

      if response and hasattr(response, "text"):
        print("💡 Gemini response received successfully!", flush=True)
      else:
        print("⚠️ Received empty response from Gemini.", flush=True)

    except Exception as e:
      print(f"❌ Gemini API Execution Error: {e}", flush=True)
  else:
    print("⚠️ Skipping scan: Gemini client not initialized.", flush=True)

  print("⏳ Scan cycle complete. Sleeping for 60 seconds...\n", flush=True)
  time.sleep(60)
