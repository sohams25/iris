#!/usr/bin/env python3
"""Post a message to Slack as the bot user (preferred) or fall back to webhook.

Why bot over webhook:
  - Identity is consistent with the bot user that handles inbound mentions
  - Replies in the posted thread are auto-tracked by the slackbot thread cache
  - chat.delete works on these messages (webhook posts can't be deleted by bot)
  - Returns the message ts so callers can thread follow-ups

Usage:
    scripts/notify.py "title" "body"
    scripts/notify.py --thread-of "1700000000.000100" "title" "body"
    scripts/notify.py --capture-ts /tmp/last_ts.txt "title" "body"

Exit codes:
    0  posted (and ts captured if requested)
    0  silently no-op (no tokens available; not an error condition)
    1  bad args
    2  Slack API error
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))
from _iris_paths import env_file

ENV_FILE = env_file()


def _load_env() -> dict[str, str]:
    out: dict[str, str] = {}
    if not ENV_FILE.exists():
        return out
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _post_bot(token: str, channel: str, title: str, body: str, thread_ts: str | None) -> dict:
    """Post via chat.postMessage. Returns the parsed Slack response."""
    payload = {
        "channel": channel,
        "text": f"*{title}*\n{body}",
        "blocks": [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*{title}*"},
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": body[:2900] if body else "_(no body)_"},
            },
        ],
        "unfurl_links": False,
        "unfurl_media": False,
    }
    if thread_ts:
        payload["thread_ts"] = thread_ts

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://slack.com/api/chat.postMessage",
        data=data,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": f"Bearer {token}",
        },
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def _post_webhook(url: str, title: str, body: str) -> bool:
    """Fallback: POST to incoming-webhook URL. No ts available."""
    payload = json.dumps({"text": f"*{title}*\n{body}"}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status == 200
    except urllib.error.URLError:
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("title")
    ap.add_argument("body", nargs="?", default="")
    ap.add_argument("--thread-of", default=None, help="thread root ts to reply under")
    ap.add_argument("--capture-ts", default=None, help="write the posted ts to this file")
    ap.add_argument("--channel", default=None, help="override channel id")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    env = {**_load_env(), **os.environ}
    bot_token = env.get("SLACK_BOT_TOKEN", "").strip()
    webhook = env.get("SLACK_WEBHOOK_URL", "").strip()
    channel = args.channel or env.get("SLACK_CHANNEL_ID", "").strip()

    # Prefer bot identity if we have both a token and a channel
    if bot_token and channel:
        try:
            res = _post_bot(bot_token, channel, args.title, args.body, args.thread_of)
        except (urllib.error.URLError, http.client.HTTPException, json.JSONDecodeError) as e:
            if not args.quiet:
                print(f"[notify] bot post failed ({e}); falling back to webhook", file=sys.stderr)
            res = {"ok": False, "error": str(e)}
        if res.get("ok"):
            ts = res.get("ts")
            if args.capture_ts and ts:
                Path(args.capture_ts).write_text(ts, encoding="utf-8")
            if not args.quiet:
                print(f"[notify] posted as bot: ts={ts}")
            return 0
        else:
            if not args.quiet:
                print(f"[notify] bot post returned not-ok: {res.get('error')}", file=sys.stderr)

    # Fallback: webhook
    if webhook:
        if _post_webhook(webhook, args.title, args.body):
            if not args.quiet:
                print("[notify] posted via webhook (no ts available)")
            return 0
        if not args.quiet:
            print("[notify] webhook post failed", file=sys.stderr)
        return 2

    # No-op (no tokens at all)
    if not args.quiet:
        print("[notify] no SLACK_BOT_TOKEN+SLACK_CHANNEL_ID and no SLACK_WEBHOOK_URL; nothing to do")
    return 0


if __name__ == "__main__":
    sys.exit(main())
