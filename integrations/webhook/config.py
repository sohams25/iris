"""Webhook adapter config — stub. See README.md."""
import os

def healthcheck() -> dict:
    return {
        "wired": False,
        "url_set": bool(os.environ.get("WEBHOOK_URL")),
        "secret_set": bool(os.environ.get("WEBHOOK_SECRET")),
    }
