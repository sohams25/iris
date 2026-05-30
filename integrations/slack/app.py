"""Slackbot entry point.

Bolt app with Socket Mode. Subscribes to:
  - app_mention events       → mentions.dispatch(text)
  - slash commands           → /loop, /tasks, /handover
  - message events (threads) → context-aware reply if message is in a known thread

Run:
  python -m integrations.slack.app
or use scripts/slackbot-start.sh.
"""
from __future__ import annotations

import logging
import os
import re
import sys
from typing import Any

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from integrations.slack.config import (
    SLACK_APP_TOKEN,
    SLACK_BOT_TOKEN,
    SLACK_CHANNEL_ID,
    channel_allowed,
)
from integrations.slack import client
from integrations.slack.handlers import commands, threads
from integrations.slack.handlers.mentions import dispatch

logging.basicConfig(
    level=os.environ.get("SLACKBOT_LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
)
log = logging.getLogger("slackbot")

app = App(token=SLACK_BOT_TOKEN, name="workspace-autonomous")


# ---------- app_mention ----------

@app.event("app_mention")
def on_mention(body: dict[str, Any], say, ack):
    event = body.get("event", {})
    channel = event.get("channel", "")
    text = event.get("text", "")
    user = event.get("user", "")
    thread_ts = event.get("thread_ts") or event.get("ts")

    if not channel_allowed(channel):
        log.info("ignoring mention from disallowed channel: %s", channel)
        return

    log.info("mention from %s in %s: %r", user, channel, text)
    try:
        reply = dispatch(text)
    except Exception as e:
        log.exception("dispatch crashed")
        reply = f"❌ Internal error: `{type(e).__name__}: {e}`"

    posted = say(text=reply, thread_ts=thread_ts)
    # If this was a fresh top-level mention (not already a thread reply),
    # remember the thread root so future replies have context.
    if event.get("thread_ts") is None and posted and posted.get("ok"):
        threads.remember(
            event.get("ts", ""),
            {"kind": "mention", "trigger_text": text, "by": user},
        )


# ---------- message events (only in threads we know about) ----------

@app.event("message")
def on_message(body: dict[str, Any], say):
    event = body.get("event", {})
    # Skip bot's own messages and message_changed/deleted subtypes
    if event.get("subtype") in {"bot_message", "message_changed", "message_deleted"}:
        return
    if event.get("bot_id"):
        return
    channel = event.get("channel", "")
    if not channel_allowed(channel):
        return
    thread_ts = event.get("thread_ts")
    if not thread_ts:
        return  # only reply in threads we've seen

    ctx = threads.recall(thread_ts)
    if not ctx:
        return  # unknown thread, stay silent

    # Only respond if the message looks task-like (no @mention required since
    # we're already in our own thread)
    text = event.get("text", "") or ""
    if not _looks_task_like(text):
        return

    log.info("threaded follow-up in known thread %s: %r", thread_ts, text)
    try:
        reply = dispatch(text)
    except Exception as e:
        log.exception("threaded dispatch crashed")
        reply = f"❌ Internal error: `{type(e).__name__}: {e}`"
    say(text=reply, thread_ts=thread_ts)


_TASK_LIKE_RE = re.compile(
    r"\b(add\s+task|task|run|start|stop|status|tasks|list|pass|block|swarm|handover|help)\b",
    re.IGNORECASE,
)


def _looks_task_like(text: str) -> bool:
    return bool(_TASK_LIKE_RE.search(text or ""))


# ---------- Slash commands ----------

@app.command("/loop")
def cmd_loop(ack, respond, command):
    ack()
    if not channel_allowed(command.get("channel_id", "")):
        respond("This command isn't allowed in this channel.")
        return
    text = command.get("text", "")
    respond(commands.loop_command(text))


@app.command("/tasks")
def cmd_tasks(ack, respond, command):
    ack()
    if not channel_allowed(command.get("channel_id", "")):
        respond("This command isn't allowed in this channel.")
        return
    text = command.get("text", "")
    respond(commands.tasks_command(text))


@app.command("/handover")
def cmd_handover(ack, respond, command):
    ack()
    if not channel_allowed(command.get("channel_id", "")):
        respond("This command isn't allowed in this channel.")
        return
    text = command.get("text", "")
    respond(commands.handover_command(text))


# ---------- Startup ----------

def main() -> int:
    if not client.health():
        log.warning(
            "iris backend health check failed. The bot will still start, but "
            "commands may fail until `python3 scripts/doctor.py` is green.",
        )
    else:
        log.info("iris backend healthy")

    log.info(
        "Channel allowlist: %s",
        SLACK_CHANNEL_ID or "(none — listening everywhere)",
    )

    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    log.info("Connecting to Slack via Socket Mode...")
    try:
        handler.start()
    except KeyboardInterrupt:
        log.info("Shutting down.")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
