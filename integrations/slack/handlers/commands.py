"""Slash command handlers.

Maps /loop /tasks /handover to the same dispatch logic used for mentions.
"""
from __future__ import annotations

from integrations.slack.handlers.mentions import dispatch


def loop_command(text: str) -> str:
    """e.g. /loop start max=20 minutes=60 dry"""
    sub = (text or "").strip().split(None, 1)
    if not sub:
        return dispatch("status")
    verb = sub[0].lower()
    tail = sub[1] if len(sub) > 1 else ""
    if verb in {"start", "run", "go", "begin"}:
        return dispatch(f"run loop {tail}")
    if verb in {"stop", "halt", "kill", "cancel"}:
        return dispatch("stop loop")
    if verb in {"status", "state"}:
        return dispatch("status")
    return dispatch(f"run loop {text}")  # fall through


def tasks_command(text: str) -> str:
    """e.g. /tasks list  or  /tasks add fix the login bug files: src/auth.ts"""
    sub = (text or "").strip().split(None, 1)
    if not sub:
        return dispatch("tasks")
    verb = sub[0].lower()
    tail = sub[1] if len(sub) > 1 else ""
    if verb in {"list", "show", "ls", ""}:
        return dispatch("tasks")
    if verb in {"add", "new", "create"}:
        return dispatch(f"add task: {tail}")
    if verb in {"pass", "done", "complete"}:
        return dispatch(f"pass {tail}")
    if verb in {"block"}:
        return dispatch(f"block {tail}")
    # Fall through: assume it's an add description
    return dispatch(f"add task: {text}")


def handover_command(text: str) -> str:
    """e.g. /handover new Web GUI v1 shipped  or  /handover current"""
    sub = (text or "").strip().split(None, 1)
    if not sub:
        return dispatch("handover current")
    verb = sub[0].lower()
    tail = sub[1] if len(sub) > 1 else ""
    if verb in {"new", "create"}:
        return dispatch(f"handover new: {tail}")
    if verb in {"current", "latest", "now", "show"}:
        return dispatch("handover current")
    return dispatch(f"handover new: {text}")
