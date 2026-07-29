"""
Sentinel Signal
----------------
Listens to a Telegram channel for new messages and sends a free push
notification via ntfy.sh whenever a message contains one of your keywords.

Setup:
1. pip install telethon requests
2. Get API credentials from https://my.telegram.org (API Development Tools)
3. Fill in the CONFIG section below
4. Run: python sentinel_signal.py
   (first run will ask you to log in with your phone number - this creates
   a local session file so you won't need to log in again)

Notifications:
- Install the ntfy app (iOS/Android) or use https://ntfy.sh in a browser
- Subscribe to the same TOPIC you set below
- That's it - no account or API key needed
"""

import asyncio
import os
import re
import sys
import threading
from datetime import datetime, timedelta

import requests
from flask import Flask
from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.sessions import StringSession

from utils import mins_to_secs_in_str

load_dotenv()

# Render (and most PaaS log collectors) capture stdout via a pipe, not a TTY,
# so Python defaults to block-buffering it. That delays/loses infrequent
# print()s (e.g. [MATCH]) behind frequent ones (e.g. [DEBUG]) that happen to
# fill the buffer. Force line buffering so every print() shows up promptly.
sys.stdout.reconfigure(line_buffering=True)

# ============ CONFIG (from environment) ============
API_ID = int(os.environ["TELEGRAM_API_ID"])   # from https://my.telegram.org
API_HASH = os.environ["TELEGRAM_API_HASH"]    # from https://my.telegram.org
SESSION_STRING = os.environ.get("SESSION_STRING", "")  # from generate_session.py
CHANNEL = int(os.environ["CHANNEL_ID"])      # e.g. 'somechannel' (no @) or the channel's numeric ID

KEYWORDS = [kw.strip() for kw in os.environ["KEYWORDS"].split(",") if kw.strip()]
AVOID_KEYWORDS = [kw.strip() for kw in os.environ.get("AVOID_KEYWORDS", "").split(",") if kw.strip()]

NTFY_TOPIC = os.environ["NTFY_TOPIC"]   # pick something unique/hard to guess
NTFY_URL = f"https://ntfy.sh/{NTFY_TOPIC}"

# How often the event loop ticks the heartbeat even with no incoming messages,
# and how stale the heartbeat can get before the health check reports down.
HEARTBEAT_INTERVAL_SECONDS = int(os.environ.get("HEARTBEAT_INTERVAL_SECONDS", mins_to_secs_in_str(5)))
STALE_THRESHOLD_SECONDS = int(os.environ.get("STALE_THRESHOLD_SECONDS", mins_to_secs_in_str(15)))
# =====================================================

client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

# Updated on every incoming message and on every heartbeat tick, so the
# health check can distinguish "process is alive" from "the Telegram event
# loop is actually still running" (e.g. after a silent disconnect).
last_seen_at = datetime.now()


def mark_alive():
    global last_seen_at
    last_seen_at = datetime.now()


# === Tiny keep-alive web server ===
app = Flask(__name__)

@app.route("/")
def health():
    age = datetime.now() - last_seen_at
    if age > timedelta(seconds=STALE_THRESHOLD_SECONDS):
        return f"Sentinel Signal stale: no heartbeat for {age}.", 503
    return "Sentinel Signal is running.", 200

def run_web_server():
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)

# ==================================

def send_notification(title: str, message: str, priority: str = "default"):
    """Send a push notification via ntfy.sh"""
    try:
        requests.post(
            NTFY_URL,
            data=message.encode("utf-8"),
            headers={
                "Title": title,
                "Priority": priority,   # min, low, default, high, urgent
                "Tags": "loudspeaker",
            },
            timeout=10,
        )
    except requests.RequestException as e:
        print(f"[!] Failed to send ntfy notification: {e}")


def _word_pattern(word: str) -> "re.Pattern":
    return re.compile(r"\b" + re.escape(word) + r"\b")


def keyword_matches(keyword: str, lowered_text: str) -> bool:
    """
    A keyword of the form "a+b" matches when "a" and "b" both appear in the
    text as whole words, with "a" occurring before "b" (not necessarily
    adjacent). A keyword of the form "a&b" matches when "a" and "b" both
    appear as whole words, in any order. Plain keywords match as a single
    whole word/phrase.
    """
    if "+" in keyword:
        parts = [p.strip().lower() for p in keyword.split("+") if p.strip()]
        if not parts:
            return False
        pos = 0
        for part in parts:
            match = _word_pattern(part).search(lowered_text, pos)
            if not match:
                return False
            pos = match.end()
        return True
    if "&" in keyword:
        parts = [p.strip().lower() for p in keyword.split("&") if p.strip()]
        if not parts:
            return False
        return all(_word_pattern(part).search(lowered_text) for part in parts)
    return _word_pattern(keyword.lower()).search(lowered_text) is not None


async def handler(event):
    mark_alive()
    text = event.raw_text or ""
    received_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[DEBUG] {received_at} New message: {text[:50]}{'...' if len(text) > 50 else ''} ")
    lowered = text.lower()

    matched = [kw for kw in KEYWORDS if keyword_matches(kw, lowered)]
    if not matched:
        return

    avoided = [kw for kw in AVOID_KEYWORDS if keyword_matches(kw, lowered)]
    if avoided:
        return

    preview = text[:200] + ("..." if len(text) > 200 else "")
    print(f"[MATCH] {matched} -> {preview}")

    send_notification(
        title=f"Keyword match: {', '.join(matched)}",
        message=preview,
        priority="high",
    )


async def heartbeat_tick():
    while True:
        await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
        mark_alive()


async def main():
    print("Sentinel Signal starting...")
    
    # Start the web server in a separate thread
    threading.Thread(target=run_web_server, daemon=True).start()
 
    async with client:
        # async for dialog in client.iter_dialogs():
        #     kind = "channel" if dialog.is_channel else ("group" if dialog.is_group else "user")
        #     print(f"{dialog.id}\t[{kind}]\t{dialog.name}")
            
        # Force-resolve and cache the entity before listening.
        # This is required even with a correct numeric ID - Telethon needs
        # to "meet" the entity once per session before it can match
        # incoming updates against it, otherwise you'll see repeated
        # "Cannot find any entity corresponding to ..." errors at runtime.
        entity = await client.get_entity(CHANNEL)
        # print(f"Resolved channel: {entity.title} (id={entity.id})")
 
        client.add_event_handler(handler, events.NewMessage(chats=entity))
        asyncio.create_task(heartbeat_tick())

        print(f"Keywords: {KEYWORDS}")
        print(f"Notifications -> {NTFY_URL}")
        print("Listening...")

        await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())