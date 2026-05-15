# 📈 Stock Alert Telegram Bot

Monitors **ONON, SPY, PLTR, SHEL** every 60 seconds and sends you a Telegram message when any stock moves ±2% from the previous day's close.

---

## 🚀 Deploy to Render (free, no credit card)

### Step 1 — Put files on GitHub
1. Go to [github.com](https://github.com) → sign up free if needed
2. Click **New repository** → name it `stock-alert-bot` → click **Create**
3. Upload these 3 files: `bot.py`, `requirements.txt`, `render.yaml`

### Step 2 — Deploy on Render
1. Go to [render.com](https://render.com) → sign up free with your GitHub account
2. Click **New → Blueprint**
3. Connect your GitHub repo `stock-alert-bot`
4. Render auto-detects `render.yaml` and sets everything up
5. Click **Apply** → deployment starts (takes ~2 minutes)

### Step 3 — Confirm it works
- Check your Telegram — you'll receive a startup message:
  > 🤖 *Stock Alert Bot started!*
- The bot is now running 24/7

---

## ⚙️ Customise alerts

In Render dashboard → your service → **Environment**:

| Variable | Default | Description |
|---|---|---|
| `THRESHOLD` | `2.0` | % change to trigger alert |
| `CHECK_INTERVAL` | `60` | Seconds between checks |

Change and save → service auto-restarts.

---

## 📱 Example alerts you'll receive

```
📈 PLTR — Palantir Tech
Up +2.34% from yesterday's close
Price: $94.20 (prev close $92.01)

📉 ONON — On Holding AG
Down -2.11% from yesterday's close
Price: $41.30 (prev close $42.20)
```

---

## 🔒 Security note
Your Telegram token is stored as an environment variable on Render — not exposed publicly.
If you ever want to revoke it, message @BotFather → `/revoke` → select your bot.
