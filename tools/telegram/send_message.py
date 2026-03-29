"""
Shared Telegram message sender for both Rasclaw (RA) and Arabelle bots.

Usage:
    from send_message import send_to_arabelle, send_to_ra

    send_to_arabelle("Hi Maganda! Good morning.")
    send_to_ra("Dashboard updated.")
"""

import os
import sys
import requests
from pathlib import Path
from datetime import datetime

# Load .env
ENV_PATH = Path("/home/ra/projects/DuberyMNL/.env")

def load_env():
    """Load environment variables from .env file."""
    if not ENV_PATH.exists():
        print(f"ERROR: .env not found at {ENV_PATH}")
        sys.exit(1)
    env = {}
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip()
    return env

ENV = load_env()

ARABELLE_BOT_TOKEN = ENV.get("ARABELLE_TG_BOT_TOKEN")
ARABELLE_CHAT_ID = ENV.get("ARABELLE_TG_CHAT_ID")
RASCLAW_BOT_TOKEN = ENV.get("RASCLAW_TG_BOT_TOKEN")
RASCLAW_CHAT_ID = ENV.get("RASCLAW_TG_CHAT_ID")


def send_telegram(bot_token, chat_id, text, parse_mode="HTML"):
    """Send a message via Telegram Bot API."""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        data = resp.json()
        if not data.get("ok"):
            print(f"Telegram API error: {data}")
            return False
        return True
    except Exception as e:
        print(f"Send failed: {e}")
        return False


CONVO_LOG = Path("/home/ra/projects/ra-dashboard/.tmp/belle_conversations.log")


def log_belle_message(sender, text):
    """Log every message that goes through Belle's chat."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    CONVO_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(CONVO_LOG, "a") as f:
        f.write(f"[{ts}] {sender}: {text}\n")


def send_to_arabelle(text, parse_mode="HTML", label="Belle"):
    """Send a message to Arabelle via her bot. Auto-logs to conversation log."""
    if not ARABELLE_BOT_TOKEN or not ARABELLE_CHAT_ID:
        print("ERROR: ARABELLE_TG_BOT_TOKEN or ARABELLE_TG_CHAT_ID not set")
        return False
    success = send_telegram(ARABELLE_BOT_TOKEN, ARABELLE_CHAT_ID, text, parse_mode)
    if success:
        log_belle_message(label, text)
    return success


def send_to_ra(text, parse_mode="HTML"):
    """Send a message to RA via Rasclaw bot."""
    if not RASCLAW_BOT_TOKEN or RASCLAW_BOT_TOKEN == "stored_in_github_secrets":
        print("WARNING: RASCLAW_TG_BOT_TOKEN not available locally")
        return False
    if not RASCLAW_CHAT_ID:
        print("ERROR: RASCLAW_TG_CHAT_ID not set")
        return False
    return send_telegram(RASCLAW_BOT_TOKEN, RASCLAW_CHAT_ID, text, parse_mode)


if __name__ == "__main__":
    # Quick test
    if len(sys.argv) > 1:
        msg = " ".join(sys.argv[1:])
        print(f"Sending to Arabelle: {msg}")
        send_to_arabelle(msg)
    else:
        print("Usage: python send_message.py <message>")
