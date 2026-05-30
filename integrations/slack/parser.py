"""Heuristic regex intent parser for @bot mentions and slash commands.

Returns a structured Intent object. Unknown messages return Intent("unknown").
The parser is intentionally strict — it would rather say "I didn't understand"
than guess wrong. Fuzzy interpretation can be added later (e.g. via Claude API).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Intent:
    kind: str  # one of: add_task, run_loop, stop_loop, status, list_tasks,
               #        pass_task, block_task, swarm, handover_new,
               #        handover_current, help, unknown
    params: dict[str, Any] = field(default_factory=dict)
    raw: str = ""


# ---------- Helpers ----------

_BOT_MENTION_RE = re.compile(r"<@[A-Z0-9]+>\s*", re.IGNORECASE)


def strip_mention(text: str) -> str:
    """Remove a leading <@USERID> mention from text."""
    return _BOT_MENTION_RE.sub("", text or "", count=1).strip()


def _parse_kv_tail(s: str) -> tuple[str, dict[str, str]]:
    """Pull `key: value` or `key=value` pairs off the input string.

    Returns (remaining_text, parsed_kv).
    Numeric keys (priority, max, minutes) accept only an integer literal.
    The `files` key accepts a comma-or-space-separated path list, terminated
    by another known key or end-of-string.

    Recognized keys are matched in this priority order so longer aliases
    (max_iterations) win over shorter ones (max).
    """
    kv: dict[str, str] = {}
    remaining = s

    NUMERIC_ALIASES = [
        ("priority", "priority"),
        ("max_iterations", "max"),
        ("max_iter", "max"),
        ("max_minutes", "minutes"),
        ("minutes", "minutes"),
        ("max", "max"),
        ("min", "minutes"),
    ]
    for alias, normalized in NUMERIC_ALIASES:
        # Whole-word match, integer literal value
        m = re.search(rf"\b{re.escape(alias)}\s*[:=]\s*(\d+)\b", remaining, re.IGNORECASE)
        if m and normalized not in kv:
            kv[normalized] = m.group(1)
            remaining = remaining[: m.start()] + remaining[m.end() :]

    # Files: list of comma-or-space-separated path-like tokens, terminated by
    # another known marker word or end-of-string.
    m = re.search(
        r"\bfiles\s*[:=]\s*([\w./\-,\s]+?)(?=\s+\b(?:priority|max|max_iter|max_iterations|minutes|min|max_minutes|dry|dry-run|dryrun)\b|$)",
        remaining,
        re.IGNORECASE,
    )
    if m:
        kv["files"] = m.group(1).strip().rstrip(",")
        remaining = remaining[: m.start()] + remaining[m.end() :]

    cleaned = re.sub(r"\s+", " ", remaining).strip()
    return cleaned, kv


def _has_word(text: str, *words: str) -> bool:
    lc = text.lower()
    return any(re.search(rf"\b{re.escape(w)}\b", lc) for w in words)


# ---------- Intent matchers ----------

def parse(text: str) -> Intent:
    raw = text or ""
    t = strip_mention(raw).strip()
    lc = t.lower()

    if not t:
        return Intent("help", raw=raw)

    if lc in {"help", "?", "commands"}:
        return Intent("help", raw=raw)

    # Loop: stop
    if re.match(r"^(stop|halt|kill|cancel)\b.*(loop|run)", lc) or re.match(r"^loop\s+(stop|halt|kill|cancel)", lc):
        return Intent("stop_loop", raw=raw)

    # Loop: start
    m = re.match(r"^(run|start|launch|kick\s*off|begin)\b\s*(?:the\s+)?(?:loop|autonomous|run)?\b(.*)", lc)
    if m and "loop" in lc:
        tail = m.group(2) or ""
        _, kv = _parse_kv_tail(tail)
        params: dict[str, Any] = {}
        if "max" in kv:
            try:
                params["max_iterations"] = int(kv["max"])
            except ValueError:
                pass
        if "minutes" in kv:
            try:
                params["max_minutes"] = int(kv["minutes"])
            except ValueError:
                pass
        if _has_word(tail, "dry", "dry-run", "dryrun"):
            params["dry_run"] = True
        return Intent("run_loop", params=params, raw=raw)

    # Status
    if lc in {"status", "state", "what's up", "whats up", "what's going on"} or re.match(r"^(status|state)\b", lc):
        return Intent("status", raw=raw)

    # Swarm preview
    if re.match(r"^(swarm|wave\s*plan|preview\s+swarm)", lc):
        return Intent("swarm", raw=raw)

    # List tasks
    if lc in {"tasks", "list", "list tasks", "backlog", "show tasks", "what's the backlog"} or re.match(r"^(list|show)\s+(tasks|backlog)", lc):
        return Intent("list_tasks", raw=raw)

    # Pass / block a task
    m = re.match(r"^(pass|complete|done)\s+(T\d{1,4})\b", t, re.IGNORECASE)
    if m:
        return Intent("pass_task", params={"task_id": m.group(2).upper()}, raw=raw)

    m = re.match(r"^block\s+(T\d{1,4})\s*[:\-]?\s*(.*)$", t, re.IGNORECASE)
    if m:
        return Intent(
            "block_task",
            params={"task_id": m.group(1).upper(), "reason": m.group(2).strip() or "no reason given"},
            raw=raw,
        )

    # Handover
    m = re.match(r"^handover\s+new\s*[:\-]?\s*(.*)$", t, re.IGNORECASE)
    if m:
        return Intent("handover_new", params={"title": m.group(1).strip()}, raw=raw)
    if re.match(r"^handover\s+(current|latest|now)\b", lc):
        return Intent("handover_current", raw=raw)
    if lc.strip() == "handover":
        return Intent("handover_current", raw=raw)

    # Add task
    m = re.match(r"^(?:add\s+)?task\s*[:\-]?\s*(.+)$", t, re.IGNORECASE)
    if m:
        body = m.group(1).strip()
        title, kv = _parse_kv_tail(body)
        files: list[str] = []
        priority: int | None = None
        if "files" in kv:
            files = [f.strip() for f in re.split(r"[,\s]+", kv["files"]) if f.strip()]
        if "priority" in kv:
            try:
                priority = int(kv["priority"])
            except ValueError:
                priority = None
        title = title.strip().rstrip(".")
        if not title:
            return Intent("unknown", raw=raw)
        params: dict[str, Any] = {"title": title}
        if files:
            params["files"] = files
        if priority is not None:
            params["priority"] = priority
        return Intent("add_task", params=params, raw=raw)

    # Fallback: explicit "add" verb on its own line + body
    m = re.match(r"^add\s+(.+)$", t, re.IGNORECASE)
    if m:
        body = m.group(1).strip()
        title, kv = _parse_kv_tail(body)
        files = [f.strip() for f in re.split(r"[,\s]+", kv.get("files", "")) if f.strip()]
        priority = None
        if "priority" in kv:
            try:
                priority = int(kv["priority"])
            except ValueError:
                pass
        title = title.strip().rstrip(".")
        if not title:
            return Intent("unknown", raw=raw)
        params = {"title": title}
        if files:
            params["files"] = files
        if priority is not None:
            params["priority"] = priority
        return Intent("add_task", params=params, raw=raw)

    return Intent("unknown", raw=raw)
