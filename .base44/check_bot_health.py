#!/usr/bin/env python3
"""Compose healthcheck for the bot service.

Reports unhealthy unless the bot process is running AND Telegram accepts its
token — a polling bot has no port to probe, so this is its real responsiveness.
Prints which check failed; never prints credential values.
"""
import json
import os
import sys
import urllib.error
import urllib.request


def bot_running():
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/cmdline", "rb") as handle:
                cmdline = handle.read().decode("utf-8", "replace")
        except OSError:
            continue
        if "chatbot.py" in cmdline:
            return True
    return False


def telegram_ok():
    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        return False, "TELEGRAM_BOT_TOKEN is not set"
    try:
        with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/getMe", timeout=6) as response:
            body = json.loads(response.read().decode("utf-8", "replace"))
        return bool(body.get("ok")), "getMe ok" if body.get("ok") else "getMe returned ok=false"
    except urllib.error.HTTPError as error:
        return False, f"getMe failed with HTTP {error.code}"
    except Exception as error:
        return False, f"getMe failed: {type(error).__name__}"


def main():
    failures = []
    if not bot_running():
        failures.append("bot process not running")
    accepted, detail = telegram_ok()
    if not accepted:
        failures.append(f"telegram: {detail}")
    if failures:
        print("unhealthy: " + "; ".join(failures))
        return 1
    print("healthy: bot process running, Telegram accepted the token")
    return 0


if __name__ == "__main__":
    sys.exit(main())
