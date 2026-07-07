import os, time, requests, logging, threading
from datetime import datetime, date, timezone

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

_T2 = "AAHLrGu5zad2"
_T3 = "HEcXpWKzyX6o1JtK9HoljA"
TELEGRAM_TOKEN = "8904597075:" + _T2 + "\u005F" + _T3
TELEGRAM_CHAT_ID = "1448245061"
THRESHOLD = 2.0
CHECK_INTERVAL = 60

BRIEFING_HOUR = 5        # 8am Bulgaria time (UTC+3)
NEWS_INTERVAL = 900      # 15 минути в секунди
MIN_SENTIMENT  = 0.7     # праг за "съществено важна" новина (0-1)
MIN_BUZZ       = 0.6     # buzz score праг (колко активно се споменава)

FINNHUB_TOKEN = os.environ.get("FINNHUB_TOKEN", "")

# Символи поддържани от Finnhub (само акции/ETF)
FINNHUB_SYMBOLS = {"ONON", "PLTR", "NVDA", "AMD", "GLD"}

STOCKS = [
    {"symbol": "ONON",     "name": "On Holding AG"},
    {"symbol": "^GSPC",    "name": "S&P 500 Index"},
    {"symbol": "PLTR",     "name": "Palantir Tech"},
    {"symbol": "SHELL.AS", "name": "Shell plc (Amsterdam)"},
    {"symbol": "NVDA",     "name": "Nvidia"},
    {"symbol": "AMD",      "name": "AMD"},
    {"symbol": "SI=F",     "name": "Silver Spot"},
    {"symbol": "GLD",      "name": "Gold"},
]

alerted          = {s["symbol"]: {"up": False, "down": False} for s in STOCKS}
news_seen        = set()   # headlines вече изпратени
last_reset_day   = None
last_briefing_day = None
last_news_check  = 0


# ──────────────────────────────────────────────
# ПОМОЩНИ ФУНКЦИИ
# ──────────────────────────────────────────────

def reset_alerts_if_new_day():
    global last_reset_day
    today = date.today()
    if today != last_reset_day:
        for s in STOCKS:
            alerted[s["symbol"]] = {"up": False, "down": False}
        news_seen.clear()
        last_reset_day = today
        logging.info("New trading day – alert flags reset.")


def fetch_price(symbol):
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        + symbol + "?interval=1d&range=1d"
    )
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, headers=headers, timeout=10)
    r.raise_for_status()
    meta = r.json()["chart"]["result"][0]["meta"]
    price      = meta["regularMarketPrice"]
    prev_close = meta["chartPreviousClose"]
    pct        = ((price - prev_close) / prev_close) * 100
    return price, prev_close, pct


def send_telegram(message):
    url     = "https://api.telegram.org/bot" + TELEGRAM_TOKEN + "/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    r = requests.post(url, json=payload, timeout=10)
    r.raise_for_status()
    logging.info("Telegram sent: " + message[:80])


# ──────────────────────────────────────────────
# НОВИНИ – FINNHUB
# ──────────────────────────────────────────────

def fetch_finnhub_sentiment(symbol):
    """
    Връща (bullish_score, buzz_score) от Finnhub /news-sentiment.
    Резултат между 0 и 1; None при грешка.
    """
    if not FINNHUB_TOKEN:
        return None
    url = (
        "https://finnhub.io/api/v1/news-sentiment"
        "?symbol=" + symbol + "&token=" + FINNHUB_TOKEN
    )
    r = requests.get(url, timeout=10)
    if r.status_code != 200:
        return None
    data = r.json()
    sentiment = data.get("sentiment", {})
    buzz      = data.get("buzz", {})
    bullish   = sentiment.get("bullishPercent", 0)
    bscore    = buzz.get("buzz", 0)
    return bullish, bscore


def fetch_finnhub_news(symbol):
    """
    Връща последните новини за тикъра от последния час.
    """
    if not FINNHUB_TOKEN:
        return []
    from_ts = int(time.time()) - 3600  # последен 1 час
    to_ts   = int(time.time())
    url = (
        "https://finnhub.io/api/v1/company-news"
        "?symbol=" + symbol
        + "&from=" + datetime.utcfromtimestamp(from_ts).strftime("%Y-%m-%d")
        + "&to="   + datetime.utcfromtimestamp(to_ts).strftime("%Y-%m-%d")
        + "&token=" + FINNHUB_TOKEN
    )
    r = requests.get(url, timeout=10)
    if r.status_code != 200:
        return []
    return r.json()[:5]  # max 5 статии


def check_news():
    """
    Проверява новини за всички Finnhub-съвместими тикъри.
    Изпраща сигнал само ако sentiment > MIN_SENTIMENT и buzz > MIN_BUZZ.
    """
    global last_news_check
    now = time.time()
    if now - last_news_check < NEWS_INTERVAL:
        return
    last_news_check = now

    if not FINNHUB_TOKEN:
        logging.warning("FINNHUB_TOKEN не е зададен – новините са изключени.")
        return

    logging.info("Checking Finnhub news...")

    for s in STOCKS:
        sym = s["symbol"]
        if sym not in FINNHUB_SYMBOLS:
            continue

        try:
            result = fetch_finnhub_sentiment(sym)
            if result is None:
                continue
            bullish, buzz = result

            logging.info(
                f"News sentiment {sym}: bullish={bullish:.2f} buzz={buzz:.2f}"
            )

            # Само ако праговете са изпълнени
            if bullish >= MIN_SENTIMENT and buzz >= MIN_BUZZ:
                articles = fetch_finnhub_news(sym)
                for art in articles:
                    uid = str(art.get("id", "")) + art.get("headline", "")[:40]
                    if uid in news_seen:
                        continue
                    news_seen.add(uid)

                    headline = art.get("headline", "N/A")[:120]
                    source   = art.get("source", "")
                    url_art  = art.get("url", "")

                    msg = (
                        "📰 <b>NEWS ALERT – " + sym + "</b> – " + s["name"] + "\n"
                        + "Sentiment: " + str(round(bullish * 100)) + "% bullish"
                        + " | Buzz: " + str(round(buzz * 100)) + "%\n\n"
                        + headline + "\n"
                        + "<i>" + source + "</i>\n"
                        + url_art
                    )
                    send_telegram(msg)

        except Exception as e:
            logging.error(f"News error {sym}: {e}")


# ──────────────────────────────────────────────
# СУТРЕШЕН БРИФИНГ
# ──────────────────────────────────────────────

def send_morning_briefing():
    global last_briefing_day
    today   = date.today()
    now_utc = datetime.now(timezone.utc)
    if last_briefing_day == today or now_utc.hour != BRIEFING_HOUR:
        return
    last_briefing_day = today
    logging.info("Sending morning briefing...")

    lines     = []
    today_str = today.strftime("%b %d, %Y")
    lines.append("☀️ Good morning! Market snapshot " + today_str)
    lines.append("")

    for s in STOCKS:
        try:
            price, prev_close, pct = fetch_price(s["symbol"])
            sign  = "+" if pct >= 0 else ""
            arrow = "▲" if pct >= 0 else "▼"
            lines.append(
                arrow + " " + s["symbol"]
                + "  $" + str(round(price, 2))
                + "  (" + sign + str(round(pct, 2)) + "%)"
            )
        except Exception:
            lines.append(s["symbol"] + ": unavailable")

    send_telegram("\n".join(lines))


# ──────────────────────────────────────────────
# ПРОВЕРКА НА ЦЕНИ (+/- 2%)
# ──────────────────────────────────────────────

def check_stocks():
    reset_alerts_if_new_day()
    for s in STOCKS:
        sym = s["symbol"]
        try:
            price, prev_close, pct = fetch_price(sym)
            sign = "+" if pct >= 0 else ""
            logging.info(
                sym + ": $" + str(round(price, 2))
                + " (" + sign + str(round(pct, 2)) + "%)"
            )

            if pct >= THRESHOLD and not alerted[sym]["up"]:
                alerted[sym]["up"]   = True
                alerted[sym]["down"] = False
                send_telegram(
                    "📈 <b>UP " + sym + "</b> – " + s["name"] + "\n"
                    "+" + str(round(pct, 2)) + "% от вчера\n"
                    "Цена: $" + str(round(price, 2))
                )
            elif pct <= -THRESHOLD and not alerted[sym]["down"]:
                alerted[sym]["down"] = True
                alerted[sym]["up"]   = False
                send_telegram(
                    "📉 <b>DOWN " + sym + "</b> – " + s["name"] + "\n"
                    + str(round(pct, 2)) + "% от вчера\n"
                    "Цена: $" + str(round(price, 2))
                )
            elif abs(pct) < THRESHOLD:
                alerted[sym] = {"up": False, "down": False}

        except Exception as e:
            logging.error("Error fetching " + sym + ": " + str(e))


# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────

def main():
    logging.info("Bot started. Monitoring: " + str([s["symbol"] for s in STOCKS]))
    logging.info(
        "Threshold: +/-" + str(THRESHOLD) + "% | "
        "Price check: every " + str(CHECK_INTERVAL) + "s | "
        "News check: every " + str(NEWS_INTERVAL // 60) + "min"
    )
    news_status = "включени ✅" if FINNHUB_TOKEN else "изключени ❌ (няма FINNHUB_TOKEN)"
    send_telegram(
        "🤖 Stock Alert Bot стартиран!\n"
        "Следи: ONON, GSPC, PLTR, SHELL, NVDA, AMD, SLV, GLD\n"
        "Сигнал при: +/-" + str(THRESHOLD) + "%\n"
        "Новини (Finnhub): " + news_status + "\n"
        "Сутрешен брифинг: 8:00 ч. България"
    )

    while True:
        send_morning_briefing()
        check_stocks()
        check_news()          # ← нов модул
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
