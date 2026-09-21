import os
import re
import time
import logging
import threading
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask
import requests

# Fallback mechanism for curl_cffi TLS impersonation
try:
    from curl_cffi import requests as async_requests
    HAS_CURL_CFFI = True
except ImportError:
    import requests as async_requests
    HAS_CURL_CFFI = False

# ---------------------------------------------------------------------------
# Logging Setup
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# ---------------------------------------------------------------------------
# Environment & Configuration Variables
# ---------------------------------------------------------------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
ODDS_API_KEY = os.getenv("ODDS_API_KEY", "")
PROXY_URL = os.getenv("PROXY_URL", "")
PORT = int(os.getenv("PORT", 10000))
SCAN_INTERVAL_SECONDS = int(os.getenv("SCAN_INTERVAL_SECONDS", 1800))
DEFAULT_BANKROLL = float(os.getenv("DEFAULT_BANKROLL", 100000))

APPROVED_NAIJA_BOOKIES = {
    "sportybet": "SportyBet 🇳🇬",
    "bet9ja": "Bet9ja 🇳🇬",
    "betking": "BetKing 🇳🇬",
    "msport": "MSport 🇳🇬",
    "1xbet": "1xBet 🇳🇬",
    "betway": "Betway 🇳🇬",
    "betano": "Betano 🇳🇬",
    "22bet": "22Bet 🇳🇬",
    "melbet": "Melbet 🇳🇬",
    "onexbet": "1xBet 🇳🇬",
    "paripesa": "PariPesa 🇳🇬",
    "megapari": "MegaPari 🇳🇬",
    "betwinner": "BetWinner 🇳🇬",
    "ilot": "ILOT Bet 🇳🇬",
    "ilotbet": "ILOT Bet 🇳🇬",
    "betbonanza": "BetBonanza 🇳🇬",
    "bangbet": "BangBet 🇳🇬"
}

PROXIES = {"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None

# ---------------------------------------------------------------------------
# Flask Web Server (Render Health Checks)
# ---------------------------------------------------------------------------
app = Flask(__name__)

@app.route('/', methods=['GET', 'HEAD'])
def health_check():
    return "Naija Arb Engine Active", 200

# ---------------------------------------------------------------------------
# Helper Functions & Normalization
# ---------------------------------------------------------------------------
def normalize_team_name(name: str) -> str:
    if not name:
        return ""
    name = name.lower()
    for word in [" fc", "fc ", " cf", "cf ", " united", " utd", " town", " city", " athletic", " ath"]:
        name = name.replace(word, "")
    return re.sub(r'[^a-z0-9]', '', name)

def get_naija_bookie_name(raw_title: str):
    clean = re.sub(r'[^a-z0-9]', '', raw_title.lower())
    for key, display_name in APPROVED_NAIJA_BOOKIES.items():
        if key in clean:
            return display_name
    return None

def format_match_date(date_val) -> str:
    if not date_val:
        return "N/A"
    try:
        if isinstance(date_val, (int, float)):
            ts = date_val / 1000.0 if date_val > 1e11 else date_val
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            return dt.strftime("%d %b %Y, %H:%M UTC")
        elif isinstance(date_val, str):
            clean_str = date_val.replace("Z", "+00:00")
            dt = datetime.fromisoformat(clean_str)
            return dt.strftime("%d %b %Y, %H:%M UTC")
    except Exception:
        pass
    return str(date_val)

# ---------------------------------------------------------------------------
# Bookmaker Data Scrapers
# ---------------------------------------------------------------------------
def fetch_sportybet():
    # Direct endpoint used by SportyBet web client
    url = "https://www.sportybet.com/api/ng/factsCenter/pcUpcomingEvents"
    params = {
        "sportId": "sr:sport:1", 
        "marketId": "1,18,60",
        "pageSize": "50"
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.sportybet.com/ng/",
        "Origin": "https://www.sportybet.com"
    }
    
    matches = []
    try:
        if HAS_CURL_CFFI:
            session = async_requests.Session(impersonate="chrome120")
            res = session.get(url, params=params, headers=headers, proxies=PROXIES, timeout=15)
        else:
            res = requests.get(url, params=params, headers=headers, proxies=PROXIES, timeout=15)

        if res.status_code == 200:
            res_data = res.json()
            if res_data.get("bizCode") == 10000:
                data = res_data.get("data", [])
                events_list = data if isinstance(data, list) else data.get("tournaments", [])
                
                for item in events_list:
                    events = item.get("events", []) if isinstance(item, dict) else []
                    for ev in events:
                        home = ev.get("homeTeamName")
                        away = ev.get("awayTeamName")
                        match_time = format_match_date(ev.get("estimateStartTime"))
                        if not home or not away: 
                            continue
                            
                        odds = {}
                        for mkt in ev.get("markets", []):
                            if str(mkt.get("id")) in ["1", "sr:market:1"]:
                                for out in mkt.get("outcomes", []):
                                    desc = str(out.get("desc", ""))
                                    price = float(out.get("odds", 0))
                                    if desc == "1": odds["Home"] = price
                                    elif desc == "X": odds["Draw"] = price
                                    elif desc == "2": odds["Away"] = price
                                    
                        if len(odds) == 3 and all(v > 1.0 for v in odds.values()):
                            matches.append({
                                "bookie": APPROVED_NAIJA_BOOKIES["sportybet"], 
                                "home": home, 
                                "away": away,
                                "match_date": match_time,
                                "norm_key": f"{normalize_team_name(home)}_{normalize_team_name(away)}", 
                                "odds": odds
                            })
        logging.info(f"[SportyBet] Fetched {len(matches)} matches.")
    except Exception as e:
        logging.warning(f"[SportyBet Error]: {e}")
    return matches

def fetch_odds_api_filtered():
    if not ODDS_API_KEY:
        logging.warning("[Odds API] ODDS_API_KEY missing.")
        return []

    url = f"https://api.the-odds-api.com/v4/sports/soccer/odds/?apiKey={ODDS_API_KEY}&regions=eu,uk&markets=h2h"
    matches = []
    try:
        res = requests.get(url, timeout=12)
        if res.status_code == 200:
            for ev in res.json():
                home, away = ev.get("home_team"), ev.get("away_team")
                match_time = format_match_date(ev.get("commence_time"))
                if not home or not away: 
                    continue
                
                norm_key = f"{normalize_team_name(home)}_{normalize_team_name(away)}"
                for bookie in ev.get("bookmakers", []):
                    raw_title = bookie.get("title")
                    naija_title = get_naija_bookie_name(raw_title)
                    if not naija_title:
                        continue

                    for mkt in bookie.get("markets", []):
                        if mkt.get("key") == "h2h":
                            odds = {}
                            for out in mkt.get("outcomes", []):
                                if out.get("name") == home: odds["Home"] = float(out.get("price", 0))
                                elif out.get("name") == away: odds["Away"] = float(out.get("price", 0))
                                elif out.get("name") == "Draw": odds["Draw"] = float(out.get("price", 0))
                            
                            if len(odds) == 3:
                                matches.append({
                                    "bookie": naija_title,
                                    "home": home,
                                    "away": away,
                                    "match_date": match_time,
                                    "norm_key": norm_key,
                                    "odds": odds
                                })
            logging.info(f"[Odds API Filtered] Fetched {len(matches)} entries.")
    except Exception as e:
        logging.warning(f"[Odds API Exception]: {e}")
    return matches

# ---------------------------------------------------------------------------
# Core Arbitrage Calculation Engine
# ---------------------------------------------------------------------------
def calculate_arbitrage():
    scrapers = [fetch_sportybet, fetch_odds_api_filtered]
    all_matches = []

    with ThreadPoolExecutor(max_workers=len(scrapers)) as executor:
        futures = [executor.submit(s) for s in scrapers]
        for future in as_completed(futures):
            all_matches.extend(future.result())

    aggregated = {}
    for m in all_matches:
        key = m["norm_key"]
        if key not in aggregated:
            aggregated[key] = {
                "display": f"{m['home']} vs {m['away']}",
                "match_date": m.get("match_date", "N/A"),
                "outcomes": {"Home": [], "Draw": [], "Away": []}
            }
        for out_type, price in m["odds"].items():
            if price > 1.0:
                aggregated[key]["outcomes"][out_type].append({"bookie": m["bookie"], "price": price})

    verified_arbs = []
    for key, data in aggregated.items():
        outs = data["outcomes"]
        if outs["Home"] and outs["Draw"] and outs["Away"]:
            best_home = max(outs["Home"], key=lambda x: x["price"])
            best_draw = max(outs["Draw"], key=lambda x: x["price"])
            best_away = max(outs["Away"], key=lambda x: x["price"])

            unique_bookies = {best_home["bookie"], best_draw["bookie"], best_away["bookie"]}
            if len(unique_bookies) < 2:
                continue

            implied_sum = (1.0 / best_home["price"]) + (1.0 / best_draw["price"]) + (1.0 / best_away["price"])

            if implied_sum < 1.0:
                roi = round(((1.0 / implied_sum) - 1.0) * 100, 2)
                payout = DEFAULT_BANKROLL / implied_sum
                profit = payout - DEFAULT_BANKROLL

                s_home = round(DEFAULT_BANKROLL / (best_home["price"] * implied_sum), 2)
                s_draw = round(DEFAULT_BANKROLL / (best_draw["price"] * implied_sum), 2)
                s_away = round(DEFAULT_BANKROLL / (best_away["price"] * implied_sum), 2)

                verified_arbs.append({
                    "fixture": data["display"],
                    "match_date": data["match_date"],
                    "roi": roi,
                    "bankroll": DEFAULT_BANKROLL,
                    "profit": round(profit, 2),
                    "stakes": {
                        "Home": {**best_home, "stake": s_home},
                        "Draw": {**best_draw, "stake": s_draw},
                        "Away": {**best_away, "stake": s_away}
                    }
                })

    return verified_arbs

# ---------------------------------------------------------------------------
# Telegram Alerts
# ---------------------------------------------------------------------------
def send_telegram(text: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try:
        res = requests.post(url, json=payload, timeout=10)
        return res.status_code == 200
    except Exception:
        return False

def format_alert(arb):
    msg = f"🇳🇬 *NAIJA SUREBET FOUND* 🇳🇬\n\n"
    msg += f"⚽ *Match*: {arb['fixture']}\n"
    msg += f"📅 *Kick-off*: {arb['match_date']}\n"
    msg += f"📈 *ROI*: *+{arb['roi']}%*\n"
    msg += f"💰 *Bankroll*: ₦{arb['bankroll']:,.2f}\n"
    msg += f"💵 *Net Profit*: *₦{arb['profit']:,.2f}*\n\n"
    msg += f"*STAKE ALLOCATION*:\n"
    for out, d in arb['stakes'].items():
        msg += f"• *{out}* @ *{d['price']}* ({d['bookie']}) ➔ Stake: *₦{d['stake']:,.2f}*\n"
    return msg

def scan_loop():
    while True:
        try:
            logging.info("--- Starting Arbitrage Engine Scan ---")
            arbs = calculate_arbitrage()
            if arbs:
                for arb in arbs:
                    send_telegram(format_alert(arb))
                logging.info(f"Scan complete: Found and sent {len(arbs)} arbitrage alerts!")
            else:
                logging.info("Scan complete: Found 0 valid arbitrage opportunities.")
        except Exception as e:
            logging.error(f"Scan loop error: {e}")
        time.sleep(SCAN_INTERVAL_SECONDS)

# ---------------------------------------------------------------------------
# Execution Entry Point
# ---------------------------------------------------------------------------
threading.Thread(target=scan_loop, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
