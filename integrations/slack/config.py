"""Slack adapter configuration.

Per the iris adapter contract (see docs/integrations.md and
integrations/README.md), this module must load cleanly when its env
vars are missing. The runtime check happens when the bot is *started*,
not at import.

`require_tokens()` does the strict validation; call it from
`app.py.main()` before starting the listener.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))
from _iris_paths import env_file

ENV_FILE = env_file()


def _load_env_file() -> dict[str, str]:
    if not ENV_FILE.exists():
        return {}
    out: dict[str, str] = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        v = v.strip().strip('"').strip("'")
        out[k.strip()] = v
    return out


_env = _load_env_file()


def _get(name: str, default: str = "") -> str:
    return os.environ.get(name) or _env.get(name, default)


SLACK_BOT_TOKEN = _get("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = _get("SLACK_APP_TOKEN")
SLACK_CHANNEL_ID = _get("SLACK_CHANNEL_ID", "")
SLACKBOT_VERBOSITY = _get("SLACKBOT_VERBOSITY", "normal").lower()


def channel_allowed(channel_id: str) -> bool:
    """Return True if the bot should respond to messages from this channel."""
    if not SLACK_CHANNEL_ID:
        return True
    return channel_id == SLACK_CHANNEL_ID


def require_tokens() -> None:
    """Raise RuntimeError if required tokens are missing.

    Call this from app.py.main() before starting the listener. Tests and
    health checks that need to import the module without the env set
    must not call this.
    """
    missing = [
        name for name, val in (
            ("SLACK_BOT_TOKEN", SLACK_BOT_TOKEN),
            ("SLACK_APP_TOKEN", SLACK_APP_TOKEN),
        ) if not val
    ]
    if missing:
        raise RuntimeError(
            f"[slackbot] required env var(s) not set: {', '.join(missing)}. "
            f"Add to .env at {ENV_FILE} or export."
        )


def healthcheck() -> dict:
    """Adapter contract: report which env pieces are configured. Never raises."""
    return {
        "wired": True,
        "bot_token_set": bool(SLACK_BOT_TOKEN),
        "app_token_set": bool(SLACK_APP_TOKEN),
        "channel_restricted": bool(SLACK_CHANNEL_ID),
    }
