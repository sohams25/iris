"""Discord adapter config — stub. See README.md."""
import os

def healthcheck() -> dict:
    return {
        "wired": False,
        "token_set": bool(os.environ.get("DISCORD_BOT_TOKEN")),
        "channel_set": bool(os.environ.get("DISCORD_CHANNEL_ID")),
    }
