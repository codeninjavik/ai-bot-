# Working on this repo (Base44 sandbox)

## What this app is
`chatbot.py` is a **Telegram bot** (`python-telegram-bot` long polling + Groq for answers).
It has **no HTTP server and no web UI**: "is it working?" means it replies in Telegram, and
it must be tested from a Telegram client, not from the preview.

## Run it
```bash
docker compose -f docker-compose.base44.yml up -d --build
docker compose -f docker-compose.base44.yml logs -f bot     # bot output
```
* `bot` — runs `pip install -r requirements.txt`, then `python -u chatbot.py`, source bind-mounted
  from the repo. There is no autoreload for this bot: after editing `chatbot.py` run
  `docker compose -f docker-compose.base44.yml restart bot` (no image rebuild needed).
* `status` — serves port 3000 (the sandbox preview port) with a read-only page that shows whether
  the credentials below are accepted and tails the bot's log. The preview cannot show the bot
  itself; use it as the "is it alive?" signal. It serves `/healthz` as JSON.

## Credentials (required to boot)
`chatbot.py` reads its credentials from the environment and exits with a clear message if either
is missing:
* `TELEGRAM_BOT_TOKEN` — new token from @BotFather (the one committed in git history is exposed).
* `GROQ_API_KEY` — from https://console.groq.com/keys (the committed one is exposed too).

They are Base44 secrets, delivered to `/run/base44/app.env` and wired in with `env_file:` — never
put them under Compose `environment:`, which would permanently outrank a later dashboard change.

## Quirks worth knowing
* `requirements.txt` is unpinned; `pip install` runs on every container start (warmed by the
  `pip-cache` volume). Pin versions if reproducibility matters.
* `GROQ_MODEL` was `llama-3.3-70b-versatile`, which Groq has retired — it fails with
  `model_not_found` and every bot reply becomes a system-error message. It is now
  `openai/gpt-oss-120b`; change that one line to switch models (see what a key can use via
  `GET https://api.groq.com/openai/v1/models`). The status page validates the name against the key.
* `api.groq.com` sits behind Cloudflare, which rejects the default Python `urllib` user agent with
  HTTP 403 `error code: 1010`. `.base44/status_server.py` therefore sends an explicit `User-Agent`;
  keep it when adding probes, and don't read a urllib 403 as a bad key (a bad key is 401).
* Several `/code*` commands render code to PNG via Pygments (`DejaVu Sans Mono` must exist in the
  image — it does in `python:3.12-slim`; a different base image may need fonts installed).
* `check_subscription` fails open by design: if the bot is not an admin of `@Codeninja_vik`, every
  user is allowed through.
* `chatbot.py` also registers `/codefile` behaviour through `/code --file` flags only.

## Verifying
```bash
docker compose -f docker-compose.base44.yml ps                 # bot should be healthy once tokens are valid
curl -s localhost:3000/healthz                                 # {"healthy": true, ...}
docker compose -f docker-compose.base44.yml exec bot python .base44/check_bot_health.py
```
A valid token makes the bot healthy; an invalid/missing one leaves it unhealthy with the reason
printed, which is the fastest way to tell a credential problem from a code problem.
