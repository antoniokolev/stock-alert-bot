from datetime import datetime, date, timezone

import threading

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

_T2 = "AAHLrGu5zad2"
_T3 = "HEcXpWKzyX6o1JtK9HoljA"
TELEGRAM_TOKEN = "8904597075:" + _T2 + "\u005F" + _T3
TELEGRAM_CHAT_ID = "1448245061"
THRESHOLD = 2.0
CHECK_INTERVAL = 60
BRIEFING_HOUR = 5  # 8am server time (Render runs on UTC — so set to 5 for 8am Bulgaria time UTC+3)

STOCKS = [
    {"symbol": "ONON",  "name": "On Holding AG"},
    {"symbol": "^GSPC", "name": "S&P 500 Index"},
    {"symbol": "PLTR",  "name": "Palantir Tech"},
    {"symbol": "SHELL.AS", "name": "Shell plc (Amsterdam)"},
    {"symbol": "NVDA",  "name": "Nvidia"},
    {"symbol": "AMD",   "name": "AMD"},
    {"symbol": "SI=F", "name": "Silver Spot"},
    {"symbol": "^VIX",  "name": "Volatility Index"},
    {"symbol": "GLD",   "name": "Gold"},
]

alerted = {s["symbol"]: {"up": False, "down": False} for s in STOCKS}
last_reset_day = None
last_briefing_day = None


def reset_alerts_if_new_day():
    global last_reset_day
    today = date.today()
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
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    r = requests.post(url, json=payload, timeout=10)
    r.raise_for_status()
    logging.info("Telegram sent: " + message[:60])


def send_morning_briefing():
    global last_briefing_day
    today = date.today()
    if last_briefing_day == today:
        return
    now_utc = datetime.now(timezone.utc)
    if now_utc.hour != BRIEFING_HOUR:
        return
    last_briefing_day = today
    logging.info("Sending morning briefing...")

    lines = []
    today_str = today.strftime("%b %d, %Y")
    lines.append("Good morning! Market snapshot " + today_str)
    lines.append("")

    for s in STOCKS:
        try:
            price, prev_close, pct = fetch_price(s["symbol"])
            sign = "+" if pct >= 0 else ""
            arrow = "UP" if pct >= 0 else "DN"
            lines.append(arrow + " " + s["symbol"] + " $" + str(round(price, 2)) + " (" + sign + str(round(pct, 2)) + "%)")
        except Exception as e:
            lines.append(s["symbol"] + ": unavailable")

    send_telegram("\n".join(lines))


def check_stocks():
    reset_alerts_if_new_day()
    for s in STOCKS:
        sym = s["symbol"]
        try:
            price, prev_close, pct = fetch_price(sym)
            sign = "+" if pct >= 0 else ""
            logging.info(sym + ": $" + str(round(price, 2)) + " (" + sign + str(round(pct, 2)) + "%)")

            if pct >= THRESHOLD and not alerted[sym]["up"]:
                alerted[sym]["up"] = True
                alerted[sym]["down"] = False
                send_telegram(
                    "UP " + sym + " - " + s["name"] + "\n"
                    "+" + str(round(pct, 2)) + "% from yesterday\n"
                    "Price: $" + str(round(price, 2))
                )
            elif pct <= -THRESHOLD and not alerted[sym]["down"]:
                alerted[sym]["down"] = True
                alerted[sym]["up"] = False
                send_telegram(
                    "DOWN " + sym + " - " + s["name"] + "\n"
                    + str(round(pct, 2)) + "% from yesterday\n"
                    "Price: $" + str(round(price, 2))
                )
            elif abs(pct) < THRESHOLD:
                alerted[sym] = {"up": False, "down": False}

        except Exception as e:
            logging.error("Error fetching " + sym + ": " + str(e))


def main():
    logging.info("Bot started. Monitoring: " + str([s["symbol"] for s in STOCKS]))
    logging.info("Threshold: +/-" + str(THRESHOLD) + "% | Interval: every " + str(CHECK_INTERVAL) + "s")
    send_telegram("Stock Alert Bot started! Monitoring: ONON, GSPC, PLTR, SHEL, NVDA, AMD, SLV, VIX, GLD at +/-" + str(THRESHOLD) + "%\nMorning briefing at 8am Bulgaria time.")
    while True:
        send_morning_briefing()
        check_stocks()
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
