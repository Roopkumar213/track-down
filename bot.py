# bot.py
import os
import logging
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from dotenv import load_dotenv
load_dotenv()

# Configuration
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    raise SystemExit("Set TELEGRAM_BOT_TOKEN env var")

# URL of your running Flask server (adjust if remote)
SERVER_BASE = os.environ.get("SERVER_BASE", "http://127.0.0.1:5000")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot ready. Use /create <label> to create a session.")

async def create(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Usage: /create myphone
    Creates a session on the Flask server and returns the link.
    """
    chat_id = update.effective_chat.id
    label = " ".join(context.args) if context.args else ""
    payload = {"label": label, "chat_id": str(chat_id)}
    try:
        r = requests.post(f"{SERVER_BASE}/create", json=payload, timeout=10)
        r.raise_for_status()
        data = r.json()
        text = f"Session created.\nToken: {data['token']}\nOpen this link on your phone: {data['link']}\nKeep permissions allowed while the page is open."
        await update.message.reply_text(text)
    except Exception as e:
        logger.exception("Error creating session")
        await update.message.reply_text(f"Failed to create session: {e}")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Usage: /status <token>
    Fetch session metadata from server.
    """
    if not context.args:
        await update.message.reply_text("Usage: /status <token>")
        return
    token = context.args[0]
    try:
        r = requests.get(f"{SERVER_BASE}/session_data/{token}", timeout=10)
        if r.status_code != 200:
            await update.message.reply_text(f"Server returned status {r.status_code}: {r.text}")
            return
        data = r.json()
        visits = data.get("visits", [])
        text = f"Session {token}\nLabel: {data.get('label')}\nCreated: {data.get('created_at')}\nTotal events: {len(visits)}"
        await update.message.reply_text(text)
        # Optionally list latest few events
        for v in visits[-5:]:
            await update.message.reply_text(f"{v['timestamp']}\nIP: {v['ip']}\nBattery: {v.get('battery')}\nCoords: {v.get('coords')}")
    except Exception as e:
        logger.exception("Error fetching status")
        await update.message.reply_text(f"Failed to fetch status: {e}")

def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("create", create))
    app.add_handler(CommandHandler("status", status))
    logger.info("Starting bot (polling)...")
    app.run_polling()

if __name__ == "__main__":
    main()
