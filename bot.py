import os, time, requests, logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "1448245061")
THRESHOLD = float(os.getenv("THRESHOLD", "2.0"))  # percent
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "60"))  # seconds

STOCKS = [
    {"symbol": "ONON", "name": "On Holding AG"},
    {"symbol": "SPY",  "name": "S&P 500 ETF"},
    {"symbol": "PLTR", "name": "Palantir Tech"},
    {"symbol": "SHEL", "name": "Shell plc"},
]

# Tracks whether we've already alerted for this direction today
alerted = {s["symbol"]: {"up": False, "down": False} for s in STOCKS}
last_reset_day = datetime.now().date()


def reset_alerts_if_new_day():
    global last_reset_day
    today = datetime.now().date()
    if today != last_reset_day:
        for s in STOCKS:
            alerted[s["symbol"]] = {"up": False, "down": False}
        last_reset_day = today
        logging.info("New trading day — alert flags reset.")


def fetch_price(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=1d"
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, headers=headers, timeout=10)
    r.raise_for_status()
    meta = r.json()["chart"]["result"][0]["meta"]
    price = meta["regularMarketPrice"]
    prev_close = meta["chartPreviousClose"]
    pct = ((price - prev_close) / prev_close) * 100
    return price, prev_close, pct


def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    r = requests.post(url, json=payload, timeout=10)
    r.raise_for_status()
    logging.info(f"Telegram sent: {message[:60]}")


def check_stocks():
    reset_alerts_if_new_day()
    for s in STOCKS:
        sym = s["symbol"]
        try:
            price, prev_close, pct = fetch_price(sym)
            sign = "+" if pct >= 0 else ""
            logging.info(f"{sym}: ${price:.2f} ({sign}{pct:.2f}%)")

            if pct >= THRESHOLD and not alerted[sym]["up"]:
                alerted[sym]["up"] = True
                alerted[sym]["down"] = False
                send_telegram(
                    f"📈 *{sym} — {s['name']}*\n"
                    f"Up *+{pct:.2f}%* from yesterday's close\n"
                    f"Price: *${price:.2f}* (prev close ${prev_close:.2f})"
                )
            elif pct <= -THRESHOLD and not alerted[sym]["down"]:
                alerted[sym]["down"] = True
                alerted[sym]["up"] = False
                send_telegram(
                    f"📉 *{sym} — {s['name']}*\n"
                    f"Down *{pct:.2f}%* from yesterday's close\n"
                    f"Price: *${price:.2f}* (prev close ${prev_close:.2f})"
                )
            elif abs(pct) < THRESHOLD:
                # Reset so it can alert again if it crosses threshold again
                alerted[sym] = {"up": False, "down": False}

        except Exception as e:
            logging.error(f"Error fetching {sym}: {e}")


def main():
    logging.info(f"Bot started. Monitoring: {[s['symbol'] for s in STOCKS]}")
    logging.info(f"Threshold: ±{THRESHOLD}% | Interval: every {CHECK_INTERVAL}s")
    send_telegram("Stock Alert Bot started! Monitoring ONON, SPY, PLTR, SHEL at +/-2%")
        f"🤖 *Stock Alert Bot started!*\n"
        f"Monitoring: ONON, SPY, PLTR, SHEL\n"
        f"Alert threshold: ±{THRESHOLD}%\n"
        f"Checking every {CHECK_INTERVAL} seconds"
    )
    while True:
        check_stocks()
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
