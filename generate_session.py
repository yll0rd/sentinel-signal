"""
Run this ONCE, locally, to log in and generate a session string.
Paste the resulting string into Render's SESSION_STRING environment variable.

Keep this string secret - it is equivalent to your Telegram login.
"""

import os

from telethon import TelegramClient
from telethon.sessions import StringSession
from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.environ["TELEGRAM_API_ID"])   # from https://my.telegram.org
API_HASH = os.environ["TELEGRAM_API_HASH"]

with TelegramClient(StringSession(), API_ID, API_HASH) as client:
    print("\nYour session string (copy everything below this line):\n")
    print(client.session.save())