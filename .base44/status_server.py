#!/usr/bin/env python3
"""Read-only status page served on the sandbox preview port (3000).

The Codeninja AI bot is a long-polling Telegram process: it has no HTTP endpoints
of its own, so nothing would be listening on the preview port and the preview
would stay blank. This tiny stdlib-only service fills that port with a live,
read-only diagnostic: are the bot's credentials accepted by Telegram and Groq,
and what is the bot process logging right now.

It never writes application state and never exposes credential values.
"""
import html
import json
import os
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("STATUS_PORT", "3000"))
LOG_FILE = os.environ.get("BOT_LOG_FILE", "/shared/bot.log")
BRAND = "Codeninja AI"


def _get_json(url, headers=None, timeout=8):
    request = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.status, json.loads(response.read().decode("utf-8", "replace"))


def _describe_http_error(error, label):
    try:
        payload = json.loads(error.read().decode("utf-8", "replace"))
        detail = payload.get("description") or payload.get("error", {}).get("message")
    except Exception:
        detail = None
    return f"{label} rejected the credential (HTTP {error.code}{': ' + str(detail) if detail else ''})"


def check_telegram():
    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        return {"ok": False, "detail": "TELEGRAM_BOT_TOKEN is not set"}
    try:
        _, body = _get_json(f"https://api.telegram.org/bot{token}/getMe")
        if body.get("ok"):
            username = body.get("result", {}).get("username", "unknown")
            return {"ok": True, "detail": f"Telegram accepted the token for @{username}"}
        return {"ok": False, "detail": f"Telegram rejected the token: {body.get('description', 'unknown')}"}
    except urllib.error.HTTPError as error:
        return {"ok": False, "detail": _describe_http_error(error, "Telegram")}
    except Exception as error:
        return {"ok": False, "detail": f"Telegram unreachable: {error}"}


def check_groq():
    key = (os.environ.get("GROQ_API_KEY") or "").strip()
    if not key:
        return {"ok": False, "detail": "GROQ_API_KEY is not set"}
    try:
        status, body = _get_json(
            "https://api.groq.com/openai/v1/models", {"Authorization": f"Bearer {key}"}
        )
        count = len(body.get("data") or [])
        return {"ok": status == 200, "detail": f"Groq accepted the key ({count} models visible)"}
    except urllib.error.HTTPError as error:
        return {"ok": False, "detail": _describe_http_error(error, "Groq")}
    except Exception as error:
        return {"ok": False, "detail": f"Groq unreachable: {error}"}


def read_log_tail(lines=25):
    try:
        with open(LOG_FILE, "r", errors="replace") as handle:
            return "".join(handle.readlines()[-lines:]).strip()
    except OSError:
        return ""


def collect_status():
    return {
        "service": BRAND,
        "telegram": check_telegram(),
        "groq": check_groq(),
        "log_tail": read_log_tail(),
    }


def render_page(status):
    rows = []
    for label, key in (("Telegram bot token", "telegram"), ("Groq API key", "groq")):
        check = status[key]
        badge = "ok" if check["ok"] else "bad"
        rows.append(
            f'<li class="{badge}"><strong>{label}</strong><span>{html.escape(check["detail"])}</span></li>'
        )
    log_tail = status["log_tail"]
    log_html = (
        f"<pre>{html.escape(log_tail)}</pre>"
        if log_tail
        else '<p class="muted">No bot output yet.</p>'
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="10">
<title>{BRAND} — bot status</title>
<style>
  :root {{ color-scheme: dark; }}
  body {{ margin: 0; padding: 2rem clamp(1rem, 5vw, 3rem); background: #0e1117; color: #e6edf3;
         font: 15px/1.6 ui-monospace, SFMono-Regular, Menlo, monospace; }}
  h1 {{ margin: 0 0 .25rem; font-size: 1.35rem; }}
  .muted {{ color: #8b949e; }}
  ul {{ list-style: none; padding: 0; margin: 1.5rem 0; display: grid; gap: .6rem; }}
  li {{ display: grid; gap: .15rem; padding: .8rem 1rem; border-radius: .6rem;
        border: 1px solid #30363d; background: #161b22; border-left-width: 4px; }}
  li.ok {{ border-left-color: #3fb950; }}
  li.bad {{ border-left-color: #f85149; }}
  li span {{ color: #8b949e; font-size: .9rem; }}
  pre {{ margin: 0; padding: 1rem; border-radius: .6rem; background: #161b22; border: 1px solid #30363d;
         max-height: 22rem; overflow: auto; white-space: pre-wrap; }}
  footer {{ margin-top: 2rem; color: #8b949e; font-size: .85rem; }}
</style>
</head>
<body>
<h1>{BRAND} — Telegram bot status</h1>
<p class="muted">This page is a read-only diagnostic for the sandbox preview. A Telegram bot has no
web interface of its own — talk to it in Telegram to use it. Refreshes every 10 seconds.</p>
<ul>
{''.join(rows)}
</ul>
<h2 style="font-size:1rem;margin:0 0 .6rem">Bot output</h2>
{log_html}
<footer>Reported by .base44/status_server.py · credentials are never displayed.</footer>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, content_type):
        payload = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/healthz":
            status = collect_status()
            healthy = status["telegram"]["ok"] and status["groq"]["ok"]
            self._send(200, json.dumps({"healthy": healthy, **status}), "application/json")
            return
        if path in ("/", "/index.html"):
            self._send(200, render_page(collect_status()), "text/html; charset=utf-8")
            return
        self._send(404, "Not found", "text/plain; charset=utf-8")

    def log_message(self, fmt, *args):
        print(f"status: {self.address_string()} {fmt % args}", flush=True)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
