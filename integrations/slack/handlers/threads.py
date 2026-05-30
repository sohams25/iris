"""Threaded-reply context tracker.

When the autonomous loop posts a notification to Slack, the bot remembers
the message's `ts` so that mentions made as a reply IN THAT THREAD can be
treated as "next-step from where the loop left off".

Storage is in-memory and intentionally bounded. Context evaporates when
the bot restarts — that's fine for an MVP. If you want durability, swap
the dict for a tiny SQLite table later.
"""
from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any

# thread_ts -> {"recorded_at": float, "context": dict}
_THREADS: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
_MAX_THREADS = 200
_TTL_SECONDS = 7 * 24 * 3600  # 1 week


def remember(thread_ts: str, context: dict[str, Any]) -> None:
    """Associate context with a thread root."""
    _THREADS[thread_ts] = {"recorded_at": time.time(), "context": context}
    _THREADS.move_to_end(thread_ts)
    while len(_THREADS) > _MAX_THREADS:
        _THREADS.popitem(last=False)


def recall(thread_ts: str | None) -> dict[str, Any] | None:
    """Return the context recorded for a thread, or None if unknown/expired."""
    if not thread_ts:
        return None
    entry = _THREADS.get(thread_ts)
    if not entry:
        return None
    if time.time() - entry["recorded_at"] > _TTL_SECONDS:
        _THREADS.pop(thread_ts, None)
        return None
    return entry["context"]


def forget(thread_ts: str) -> None:
    _THREADS.pop(thread_ts, None)
