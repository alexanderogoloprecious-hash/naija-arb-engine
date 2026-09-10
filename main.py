import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


class HealthCheckHandler(BaseHTTPRequestHandler):

  def do_GET(self):
    self.send_response(200)
    self.end_headers()
    self.wfile.write(b"OK")

  def do_HEAD(self):
    self.send_response(200)
    self.end_headers()


def start_health_server():
  port = int(os.environ.get("PORT", 10000))
  server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
  server.serve_forever()


threading.Thread(target=start_health_server, daemon=True).start()
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler


# Dummy server to pass Render's port check
class HealthCheckHandler(BaseHTTPRequestHandler):

  def do_GET(self):
    self.send_response(200)
    self.end_headers()
    self.wfile.write(b"OK")


def start_health_server():
  port = int(os.environ.get("PORT", 10000))
  server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
  server.serve_forever()


threading.Thread(target=start_health_server, daemon=True).start()
import os
import time
import requests
from google import genai
from google.genai import types

# Load credentials from environment variables
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

SYSTEM_INSTRUCTION = """
You are "NaijaArbEngine-Pro", an ultra-low-latency sports betting arbitrage engine for Nigerian sportsbooks (SportyBet, Bet9ja, etc.).
Evaluate input odds feeds for arbitrage. If found, return JSON output with profit margins and ₦100 rounded stakes for a ₦100,000 bankroll.
"""

client = genai.Client(api_key=GEMINI_API_KEY)

def send_telegram_alert(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Failed to send Telegram alert: {e}")

def run_scanner_loop():
    print("NaijaArbEngine-Pro worker active. Scanning for surebets...")
    
    # Placeholder sample payload (Replace this with live Parse API odds endpoint)
    sample_odds = [
        {"bookmaker": "SportyBet", "match": "3SC vs Enyimba Aba", "market": "Over/Under 2.5", "outcomes": [{"name": "Over 2.5", "odds": 2.25}]},
        {"bookmaker": "Bet9ja", "match": "Shooting Stars vs Enyimba Int", "market": "Over/Under 2.5", "outcomes": [{"name": "Under 2.5", "odds": 1.98}]}
    ]

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=str(sample_odds),
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            temperature=0.1
        )
    )

    if "ARBITRAGE_FOUND" in response.text:
        send_telegram_alert(f"🚨 **Arbitrage Alert Found!** 🚨\n\n```json\n{response.text}\n```")

if __name__ == "__main__":
    # Test telegram on boot
    send_telegram_alert("🚀 *NaijaArbEngine-Pro initialized and monitoring...*")
    
    while True:
        try:
            run_scanner_loop()
        except Exception as e:
            print(f"Error during scan: {e}")
        
        # Scan frequency (every 15 seconds)
        time.sleep(15)
