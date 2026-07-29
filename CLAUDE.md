# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Sentinel Signal is a single-process script that listens to a Telegram channel via Telethon and
sends a free push notification through ntfy.sh whenever a new message matches configured
keywords (and doesn't match an avoid-list). It's meant to run continuously (e.g. on Render) with
a tiny Flask endpoint just to satisfy host health checks / keep-alive pings.

There is no build step, test suite, or package structure — it's two scripts:
- [app.py](app.py) — the long-running listener
- [generate_session.py](generate_session.py) — one-time local login helper

## Setup & running

```
pip install -r requirements.txt
python generate_session.py   # run once locally, logs into Telegram interactively,
                              # prints a SESSION_STRING to paste into .env / host env vars
python app.py                # starts the listener (and a keep-alive web server on $PORT)
```

Configuration is entirely via environment variables (loaded from `.env` via python-dotenv — see
[.env.example](.env.example)):
- `TELEGRAM_API_ID`, `TELEGRAM_API_HASH` — from https://my.telegram.org
- `SESSION_STRING` — produced by `generate_session.py`; equivalent to a Telegram login, must stay secret
- `CHANNEL_ID` — numeric ID of the channel to watch
- `KEYWORDS` — comma-separated, case-insensitive substring match
- `AVOID_KEYWORDS` — comma-separated, case-insensitive; if any hit, the notification is suppressed
- `NTFY_TOPIC` — the ntfy.sh topic to publish to (subscribe to the same topic in the ntfy app)
- `PORT` — optional, defaults to 8080, used only by the keep-alive Flask server
- `HEARTBEAT_INTERVAL_SECONDS` — optional, defaults to 300; how often the event loop ticks the
  heartbeat when no messages are arriving
- `STALE_THRESHOLD_SECONDS` — optional, defaults to 900; how stale the heartbeat can get before
  the `/` health check reports 503

There are no automated tests, lint config, or CI in this repo.

## Architecture notes

- `app.py` runs two things concurrently: the Telethon client event loop (`main()`, via
  `asyncio.run`) and a Flask app (`run_web_server`) started in a daemon thread purely so hosts
  like Render see an open port and don't kill the process.
- The `/` health check is a real liveness check, not a dumb 200: `last_seen_at` is updated by every
  incoming message (`handler`) and by a periodic `heartbeat_tick()` background task (so a quiet
  channel doesn't look like an outage), and `/` returns 503 once `last_seen_at` is older than
  `STALE_THRESHOLD_SECONDS`. This exists so an external keep-alive pinger (needed to stop Render's
  free-tier Web Service from spinning down after 15 idle minutes) doubles as an outage alarm — it
  catches a silent Telethon disconnect, not just a dead process.
- Before registering the `NewMessage` event handler, the code explicitly calls
  `client.get_entity(CHANNEL)` to force-resolve and cache the channel entity. This is required —
  even with a correct numeric channel ID, Telethon needs to "meet" an entity once per session
  before incoming updates will match against it, otherwise you get repeated "Cannot find any
  entity corresponding to ..." errors at runtime. Don't remove this call.
- Keyword matching (`keyword_matches` in app.py) is case-insensitive and whole-word (`\b`-bounded
  regex), not a raw substring check — `"art"` matches `"modern art"` but not `"start"`. A keyword
  written as `a+b` matches when `a` and `b` both appear as whole words with `a` occurring before
  `b` (not necessarily adjacent); `a&b` matches when both appear as whole words in any order.
  This applies to both `KEYWORDS` and `AVOID_KEYWORDS`.
- Session state persists locally as `*.session` / `*.session-journal` files (SQLite) when not
  using `SESSION_STRING`; these and `.env` are gitignored since both are credential-equivalent.
