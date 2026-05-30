#!/usr/bin/env python3
"""Autonomous takeover — the toggle, budgets, kill-switch, and audit trail.

`/takeover on` flips this state to `on` and the command's self-prompting loop
begins. The loop calls `step` at the top of every cycle: that increments the
cycle, enforces the budgets, and reports the kill-switch — the single gate the
loop polls. `/takeover off` flips state to `off`; the next `step` stops the loop.

State + audit live under the gitignored `.iris-state/takeover/`.

Subcommands:
    on [--budget-cycles 50] [--budget-minutes 480] start takeover (0 = unlimited)
    off [--reason R]                              kill-switch (loop stops next step)
    step [--progress N]                           per-cycle gate: continue (0) or stop (3)
    log "..."                                      append a decision to the audit log
    status [--json]                               mode, cycles, budgets, last stop
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _iris_paths import lock, takeover_dir

STAGNATION_LIMIT = 3   # consecutive zero-progress cycles before we stop


def _state_path() -> Path:
    return takeover_dir() / "state.json"


def _load() -> dict:
    p = _state_path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"mode": "off", "cycles": 0, "stagnant": 0,
            "budget_cycles": 0, "budget_minutes": 0,
            "started_at": None, "stop_reason": None}


def _save(state: dict) -> None:
    p = _state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(p)


def _elapsed_minutes(state: dict) -> float:
    if not state.get("started_at"):
        return 0.0
    try:
        start = datetime.fromisoformat(state["started_at"])
    except ValueError:
        return 0.0
    return (datetime.now() - start).total_seconds() / 60.0


def cmd_on(budget_cycles: int, budget_minutes: int) -> int:
    state = {"mode": "on", "cycles": 0, "stagnant": 0,
             "budget_cycles": budget_cycles, "budget_minutes": budget_minutes,
             "started_at": datetime.now().isoformat(), "stop_reason": None}
    _save(state)
    print(f"takeover ON — budgets: {budget_cycles or '∞'} cycles / {budget_minutes or '∞'} min")
    return 0


def cmd_off(reason: str) -> int:
    state = _load()
    state["mode"] = "off"
    state["stop_reason"] = reason or "user"
    _save(state)
    print(f"takeover OFF ({state['stop_reason']})")
    return 0


def cmd_step(progress: int) -> int:
    """Per-cycle gate. Exit 0 = continue, 3 = stop (and flip mode off). Held
    under a file lock so concurrent callers can't race the budget/kill-switch.
    A missing --progress counts as zero — stagnation can never be bypassed."""
    with lock(_state_path()):
        state = _load()
        if state.get("mode") != "on":
            print(f"stop: killed ({state.get('stop_reason') or 'off'})")
            return 3

        state["cycles"] = int(state.get("cycles", 0)) + 1

        stop = None
        bm = int(state.get("budget_minutes") or 0)
        bc = int(state.get("budget_cycles") or 0)
        if bm and _elapsed_minutes(state) >= bm:
            stop = "time budget"
        elif bc and state["cycles"] > bc:
            stop = "cycle budget"
        else:
            state["stagnant"] = state.get("stagnant", 0) + 1 if progress == 0 else 0
            if state["stagnant"] >= STAGNATION_LIMIT:
                stop = "stagnation"

        if stop:
            state["mode"] = "off"
            state["stop_reason"] = stop
            _save(state)
            print(f"stop: {stop}")
            return 3

        _save(state)
        print(f"continue (cycle {state['cycles']})")
        return 0


def cmd_log(text: str) -> int:
    p = takeover_dir() / "log.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    rec = {"ts": datetime.now().isoformat(), "text": text}
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    return 0


def cmd_status(as_json: bool) -> int:
    state = _load()
    if as_json:
        print(json.dumps({**state, "elapsed_minutes": round(_elapsed_minutes(state), 1)}))
        return 0
    print(f"takeover: {state.get('mode', 'off').upper()}")
    print(f"  cycles  : {state.get('cycles', 0)}"
          + (f" / {state['budget_cycles']}" if state.get("budget_cycles") else ""))
    print(f"  elapsed : {_elapsed_minutes(state):.1f} min"
          + (f" / {state['budget_minutes']}" if state.get("budget_minutes") else ""))
    if state.get("stop_reason"):
        print(f"  stopped : {state['stop_reason']}")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="takeover.py")
    sub = ap.add_subparsers(dest="cmd")
    on = sub.add_parser("on")
    on.add_argument("--budget-cycles", type=int, default=50)
    on.add_argument("--budget-minutes", type=int, default=480)
    off = sub.add_parser("off")
    off.add_argument("--reason", default="user")
    stp = sub.add_parser("step")
    stp.add_argument("--progress", type=int, default=0)
    lg = sub.add_parser("log")
    lg.add_argument("text")
    stt = sub.add_parser("status")
    stt.add_argument("--json", action="store_true")
    args = ap.parse_args(argv[1:])

    if args.cmd == "on":
        return cmd_on(args.budget_cycles, args.budget_minutes)
    if args.cmd == "off":
        return cmd_off(args.reason)
    if args.cmd == "step":
        return cmd_step(args.progress)
    if args.cmd == "log":
        return cmd_log(args.text)
    if args.cmd == "status":
        return cmd_status(args.json)
    ap.print_help(sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
