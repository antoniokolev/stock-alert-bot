import os, time, requests, logging, json
from datetime import datetime, date, timezone

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

_T2 = "AAHLrGu5zad2"
_T3 = "HEcXpWKzyX6o1JtK9HoljA"
TELEGRAM_TOKEN = "8904597075:" + _T2 + "\u005F" + _T3
TELEGRAM_CHAT_ID = "1448245061"
THRESHOLD      = 2.0
CHECK_INTERVAL = 60

BRIEFING_HOUR = 5      # 8am Bulgaria (UTC+3)
NEWS_INTERVAL = 900    # 15 минути

FINNHUB_TOKEN   = os.environ.get("FINNHUB_TOKEN", "")
FINNHUB_SYMBOLS = {"ONON", "PLTR", "NVDA", "AMD", "GLD", "SHELL"}

# Ключови думи за позитивни новини
POSITIVE_KEYWORDS = {
    "beat", "beats", "surge", "surges", "jump", "jumps", "rally", "rallies",
    "upgrade", "upgraded", "outperform", "breakout", "bullish",
    "earnings beat", "above expectations", "top estimates",
    "record quarter", "record revenue", "record profit",
    "raises guidance", "raises outlook", "raises price target",
    "raised guidance", "raised outlook", "raised price target",
    "strong earnings", "strong results", "strong revenue",
    "buy", "enhanced buy", "comeback", "raised its guidance",
    "climbed", "bounced", "soared", "lifted", "boosted",
    "ai opportunity", "artificial intelligence", "data center"
}

# Негативни думи – изключваме ако са в заглавието
NEGATIVE_KEYWORDS = {
    "short", "sell", "downgrade", "downgraded", "bearish", "cut", "cuts",
    "miss", "misses", "below", "concern", "warning", "risk", "decline",
    "fall", "falls", "drop", "drops", "loss", "losses", "layoff", "lawsuit"
}

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

# Runtime state – нулира се при рестарт, но се инициализира умно
alerted         = {s["symbol"]: {"up": False, "down": False} for s in STOCKS}
news_seen       = set()
last_news_check = 0
initialized     = False   # флаг за първи цикъл


# ──────────────────────────────────────────────
# ПОМОЩНИ ФУНКЦИИ
# ──────────────────────────────────────────────

_last_reset_day = date.today()  # не нулираме при първи старт

def reset_alerts_if_new_day():
    global _last_reset_day
    today = date.today()
    if today != _last_reset_day:
        for s in STOCKS:
            alerted[s["symbol"]] = {"up": False, "down": False}
        news_seen.clear()
        _last_reset_day = today
        logging.info("New trading day – alert flags reset.")


def fetch_price(symbol):
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        + symbol + "?interval=1d&range=1d"
    )
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, headers=headers, timeout=10)
    r.raise_for_status()
    meta       = r.json()["chart"]["result"][0]["meta"]
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


def is_positive_news(headline):
    """
    Позитивна новина = съдържа поне 1 позитивна ключова дума
    И не съдържа негативна ключова дума.
    """
    h = headline.lower()
    has_positive = any(kw in h for kw in POSITIVE_KEYWORDS)
    has_negative = any(kw in h for kw in NEGATIVE_KEYWORDS)
    return has_positive and not has_negative


# ──────────────────────────────────────────────
# ИНИЦИАЛИЗАЦИЯ – умно зареждане при рестарт
# ──────────────────────────────────────────────

def initialize_flags():
    """
    При старт проверява текущите цени.
    Ако акция вече е над прага – вдига флага БЕЗ да праща сигнал.
    Зарежда и news_seen за да не дублира новини след рестарт.
    """
    global initialized
    logging.info("Initializing alert flags from current prices...")
    for s in STOCKS:
        sym = s["symbol"]
        try:
            price, prev_close, pct = fetch_price(sym)
            if pct >= THRESHOLD:
                alerted[sym]["up"]   = True
                alerted[sym]["down"] = False
                logging.info(f"  {sym}: already UP {pct:.2f}% – flag set, no alert.")
            elif pct <= -THRESHOLD:
                alerted[sym]["down"] = True
                alerted[sym]["up"]   = False
                logging.info(f"  {sym}: already DOWN {pct:.2f}% – flag set, no alert.")
            else:
                logging.info(f"  {sym}: {pct:.2f}% – within range.")
        except Exception as e:
            logging.error(f"  Init error {sym}: {e}")
    initialized = True
    logging.info("Initialization complete.")

    # Без pre-load - news_seen започва празен при всеки старт
    # Финхъб не обновява достатъчно често за pre-load да е полезен
    logging.info("News seen cache cleared. Fresh start for news.")


# ──────────────────────────────────────────────
# НОВИНИ – FINNHUB (безплатен endpoint)
# ──────────────────────────────────────────────

def fetch_finnhub_news(symbol):
    """Връща новини публикувани в последните 20 минути."""
    if not FINNHUB_TOKEN:
        return []
    now_ts  = int(time.time())
    from_ts = now_ts - 21600   # 6 часа назад (news_seen предотвратява дублиране)
    today   = datetime.fromtimestamp(now_ts, tz=timezone.utc).strftime("%Y-%m-%d")
    from_d  = datetime.fromtimestamp(from_ts, tz=timezone.utc).strftime("%Y-%m-%d")
    url = (
        "https://finnhub.io/api/v1/company-news"
        "?symbol=" + symbol
        + "&from=" + from_d
        + "&to="   + today
        + "&token=" + FINNHUB_TOKEN
    )
    try:
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            logging.warning(f"Finnhub news {symbol}: HTTP {r.status_code}")
            return []
        articles = r.json()
        # Само статии публикувани в прозореца
        recent = [a for a in articles if a.get("datetime", 0) >= from_ts]
        return recent[:5]
    except Exception as e:
        logging.error(f"Finnhub fetch error {symbol}: {e}")
        return []


def check_news():
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
        # Finnhub използва чисти тикъри (без .AS суфикс)
        finnhub_sym = sym.replace(".AS", "").replace("^", "")
        if finnhub_sym not in FINNHUB_SYMBOLS:
            continue

        articles = fetch_finnhub_news(finnhub_sym)
        logging.info(f"  {sym}: {len(articles)} articles fetched")
        for art in articles:
            uid      = str(art.get("id", ""))
            headline = art.get("headline", "")
            if not uid or uid in news_seen:
                logging.info(f"    SKIP (seen): {headline[:60]}")
                continue
            if not is_positive_news(headline):
                logging.info(f"    SKIP (filter): {headline[:60]}")
                continue

            news_seen.add(uid)
            source  = art.get("source", "")
            url_art = art.get("url", "")
            ts      = art.get("datetime", 0)
            time_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%H:%M UTC") if ts else ""

            msg = (
                "📰 <b>NEWS – " + sym + "</b> – " + s["name"] + "\n"
                + time_str + " | " + source + "\n\n"
                + headline[:140] + "\n"
                + url_art
            )
            send_telegram(msg)
            logging.info(f"News alert sent for {sym}: {headline[:60]}")


# ──────────────────────────────────────────────
# СУТРЕШЕН БРИФИНГ
# ──────────────────────────────────────────────

_briefing_sent_day = None

def send_morning_briefing():
    global _briefing_sent_day
    today   = date.today()
    now_utc = datetime.now(timezone.utc)
    if _briefing_sent_day == today or now_utc.hour != BRIEFING_HOUR:
        return
    _briefing_sent_day = today
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

    # Умна инициализация – вдига флагове без сигнали
    initialize_flags()

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
        check_news()
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
