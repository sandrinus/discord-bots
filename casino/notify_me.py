import os
import sys
import traceback
import requests

WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_ALERT")
PING_UID = os.getenv("MY_DISCORD_UID")  # numeric ID as string

def notify_crash(message: str):
    if not WEBHOOK_URL:
        print("DISCORD_WEBHOOK_ALERT not set", flush=True)
        return

    payload = {
        "content": f"<@{PING_UID}> 🚨 **Casino Bot Failed to Start**\n```{message}```"
    }

    try:
        r = requests.post(WEBHOOK_URL, json=payload, timeout=5)
        if r.status_code != 204:
            print(f"Webhook failed: {r.status_code} {r.text}", flush=True)
    except Exception as e:
        print(f"Failed to send webhook: {e}", flush=True)

try:
    # This must import the file that STARTS your bot
    import main
except Exception:
    notify_crash(traceback.format_exc())
    sys.exit(1)
