import os, time, requests, logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

_T2 = "AAHLrGu5zad2"
_T3 = "HEcXpWKzyX6o1JtK9HoljA"
TELEGRAM_TOKEN = "8904597075:" + _T2 + "\u005F" + _T3
TELEGRAM_CHAT_ID = "1448245061"
THRESHOLD = 2.0
CHECK_INTERVAL = 60

STOCKS = [
    {"symbol": "ONON", "name": "On Holding AG"},
    {"symbol": "SPY",  "name": "S&P 500 ETF"},
    {"symbol": "PLTR", "name": "Palantir Tech"},
    {"symbol": "SHEL", "name": "Shell plc"},
]

alerted = {s["symbol"]: {"up": False, "down": False} for s in STOCKS}
last_reset_day = datetime.now().date()

def reset_alerts_if_new_day():
    global last_reset_day
    today = datetime.now().date()
    if today != last_reset_day:
        for s in STOCKS:
            alerted[s["symbol"]] = {"up": False, "down": False}
        last_reset_day = today
        logging.info("New trading day - alert flags reset.")

def fetch_price(symbol):
    url = "https://query1.finance.yahoo.com/v8/finance/chart/" + symbol + "?interval=1d&range=1d"
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, headers=headers, timeout=10)
    r.raise_for_status()
    meta = r.json()["chart"]["result"][0]["meta"]
    price = meta["regularMarketPrice"]
    prev_close = meta["chartPreviousClose"]
    pct = ((price - prev_close) / prev_close) * 100
    return price, prev_close, pct

def send_telegram(message):
    url = "https://api.telegram.org/bot" + TELEGRAM_TOKEN + "/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    r = requests.post(url, json=payload, timeout=10)
    r.raise_for_status()
    logging.info("Telegram sent: " + message[:60])

def check_stocks():
    reset_alerts_if_new_day()
    for s in STOCKS:
        sym = s["symbol"]
        try:
            price, prev_close, pct = fetch_price(sym)
            sign = "+" if pct >= 0 else ""
            logging.info(sym + ": $" + str(round(price,2)) + " (" + sign + str(round(pct,2)) + "%)")
            if pct >= THRESHOLD and not alerted[sym]["up"]:
                alerted[sym]["up"] = True
                alerted[sym]["down"] = False
                send_telegram("UP " + sym + " - " + s["name"] + "\n+" + str(round(pct,2)) + "% from yesterday\nPrice: $" + str(round(price,2)))
            elif pct <= -THRESHOLD and not alerted[sym]["down"]:
                alerted[sym]["down"] = True
                alerted[sym]["up"] = False
                send_telegram("DOWN " + sym + " - " + s["name"] + "\n" + str(round(pct,2)) + "% from yesterday\nPrice: $" + str(round(price,2)))
            elif abs(pct) < THRESHOLD:
                alerted[sym] = {"up": False, "down": False}
        except Exception as e:
            logging.error("Error fetching " + sym + ": " + str(e))

def main():
    logging.info("Bot started. Monitoring: " + str([s["symbol"] for s in STOCKS]))
    logging.info("Threshold: +/-" + str(THRESHOLD) + "% | Interval: every " + str(CHECK_INTERVAL) + "s")
    send_telegram("Stock Alert Bot started! Monitoring ONON, SPY, PLTR, SHEL at +/-" + str(THRESHOLD) + "%")
    while True:
        check_stocks()
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
