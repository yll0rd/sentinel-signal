# Sentinel Signal

Listens to a Telegram channel for new messages and sends a free push notification via
[ntfy.sh](https://ntfy.sh) whenever a message contains one of your keywords (and doesn't contain
one of your "avoid" keywords).

No paid services, no accounts beyond Telegram + ntfy, and no polling — it reacts to messages in
real time via Telethon's event system.

## How it works

1. A Telethon client logs into your Telegram account (using a saved session, so you only log in
   once) and subscribes to `NewMessage` events on a specific channel.
2. Every incoming message is checked, case-insensitively, for whole-word matches against your
   `KEYWORDS` list. A keyword can also be written as `a+b`, which matches when both `a` and `b`
   appear in the message as whole words with `a` occurring before `b` (not necessarily adjacent),
   or as `a&b`, which matches when both appear as whole words in any order.
3. If a message matches a keyword and does **not** match anything in `AVOID_KEYWORDS`, a push
   notification is fired off to a topic on ntfy.sh.
4. A minimal Flask server runs alongside the listener purely so that hosting platforms (e.g.
   Render) see an open port and treat the service as healthy — it has no other role.

## Requirements

- Python 3.9+
- A Telegram account
- API credentials from [my.telegram.org](https://my.telegram.org) (API Development Tools)
- The [ntfy](https://ntfy.sh/) app (iOS/Android) or the web client at https://ntfy.sh, subscribed
  to a topic of your choosing

## Setup

1. Create and activate a virtual environment:

   **macOS / Linux**

   ```
   python3 -m venv venv
   source venv/bin/activate
   ```

   **Windows (PowerShell)**

   ```
   python -m venv venv
   venv\Scripts\Activate.ps1
   ```

   **Windows (cmd.exe)**

   ```
   python -m venv venv
   venv\Scripts\activate.bat
   ```

2. Install dependencies:

   ```
   pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env` and fill in the values:

   ```
   cp .env.example .env
   ```

   | Variable          | Description                                                                 |
   | ------------------ | ---------------------------------------------------------------------------- |
   | `TELEGRAM_API_ID`   | From my.telegram.org (API Development Tools)                                 |
   | `TELEGRAM_API_HASH` | From my.telegram.org                                                         |
   | `CHANNEL_ID`        | Numeric ID of the channel to watch                                           |
   | `KEYWORDS`          | Comma-separated, case-insensitive whole-word/phrase matches; use `a+b` for `a` then `b` in sequence, or `a&b` for both in any order |
   | `AVOID_KEYWORDS`    | Comma-separated, case-insensitive substrings that suppress a match if present (optional) |
   | `NTFY_TOPIC`        | Pick something unique/hard to guess — anyone who knows it can read your notifications |
   | `SESSION_STRING`    | Filled in after step 4 below                                                 |
   | `PORT`              | Port for the keep-alive web server (optional, defaults to `8080`)            |

   Finding a channel's numeric ID: temporarily uncomment the `iter_dialogs()` loop in `app.py`'s
   `main()` function, run `python app.py` once, and read the ID from the printed list of dialogs.

4. Generate a session string (run this once, locally):

   ```
   python generate_session.py
   ```

   This logs you into Telegram interactively (phone number + code, and 2FA password if enabled)
   and prints a session string. Paste it into `SESSION_STRING` in your `.env` (or into your
   hosting provider's environment variables). Treat this string as equivalent to your Telegram
   login — never commit it or share it.

5. Run the listener:

   ```
   python app.py
   ```

   On success you'll see the resolved keyword list and a "Listening..." message. New matching
   messages are logged to stdout and pushed to your ntfy topic.

## Deploying

The app is designed to run as a long-lived background worker (e.g. on [Render](https://render.com)):

- Set all the variables from the table above as environment variables on the host.
- Point the start command at `python app.py`.
- Because the app binds a Flask server to `$PORT`, it satisfies host health checks that expect an
  HTTP service, even though the actual work happens via the Telegram event loop.

## Notes & gotchas

- Keyword matching is case-insensitive and whole-word (using `\b` regex boundaries), not a raw
  substring check — `"art"` will match `"modern art"` but not `"start"`.
- A keyword containing `+`, e.g. `"restock+ps5"`, matches only if all parts appear as whole words
  in the message in that order — `"restock"` must occur before `"ps5"` somewhere later in the
  text.
- A keyword containing `&`, e.g. `"restock&ps5"`, matches if all parts appear as whole words
  anywhere in the message, regardless of order.
- Both apply to `KEYWORDS` and `AVOID_KEYWORDS`.
- The app force-resolves the channel entity with `client.get_entity()` before listening. This is
  required by Telethon even when you already have the correct numeric channel ID — without it,
  incoming updates won't match and you'll see repeated "Cannot find any entity corresponding to
  ..." errors.
- Local session files (`*.session`, `*.session-journal`) and `.env` are gitignored since both are
  credential-equivalent — don't commit them.

## Project structure

| File                    | Purpose                                                        |
| ------------------------ | ---------------------------------------------------------------- |
| `app.py`                 | Main listener: Telegram event handling, keyword matching, ntfy notifications, keep-alive server |
| `generate_session.py`    | One-time local script to log in and produce a `SESSION_STRING`   |
| `requirements.txt`       | Python dependencies                                               |
| `.env.example`           | Template for required environment variables                      |
