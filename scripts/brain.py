#!/usr/bin/env python3
"""Second brain — a file-based, reward-driven model of your behaviour.

It stores "instincts" (learned preferences) distilled from your prompt language
and the decisions iris makes, updates their confidence with a reinforcement
rule on outcomes, and simulates what you'd choose at a decision point. Built to
survive long projects: experience replay + consolidation (EWC-style) + decay
keep an established pattern from being forgotten as new ones are learned —
replay rehearses each instinct's own recorded reward history.

Storage (gitignored, never committed):
    .iris-state/second-brain/   per-project instincts, replay reservoir, log
    ~/.iris/second-brain/       global tier — patterns seen across 2+ projects

Subcommands:
    observe  --domain D --pattern "..." [--id ID]   record / upsert an instinct
    reward   ID R                                    RL update (R in [-1, 1])
    simulate --domain D [--context "..."] [--json]   top instinct = what you'd pick
    recall   --domain D [--json]                     all relevant instincts
    decay                                            fade stale confidence (graceful)
    promote                                          surface >=2-project patterns
    status   [--json]                                show the brain
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _iris_paths import brain_dir, global_brain_dir, lock, repo_root

# --- policy constants -------------------------------------------------------
ALPHA = 0.34          # learning rate
C_INIT = 0.5          # confidence of a freshly observed instinct
C_MIN, C_MAX = 0.10, 0.98   # confidence floor == decay floor (one invariant)
C_FLOOR = C_MIN       # decay never drops below this — graceful, not catastrophic
P_MIN = 0.05          # minimum plasticity (most consolidated)
P_K = 0.35            # consolidation rate: plasticity = 1 / (1 + P_K * evidence)
DECAY_RATE = 0.12     # fraction of the gap-to-floor shed per decay step
REPLAY_K = 6          # past samples rehearsed per reward
REPLAY_FACTOR = 0.4   # rehearsal strength relative to a live reward
REPLAY_CAP = 500      # reservoir size
PROMOTE_PROJECTS = 2  # seen in this many projects -> promote to the global tier

_rng = random.Random(int(os.environ["BRAIN_SEED"])) if os.environ.get("BRAIN_SEED") else random.Random()


def _today() -> str:
    return date.today().isoformat()


def _project_id() -> str:
    return hashlib.sha1(str(repo_root()).encode()).hexdigest()[:12]


def _slug(s: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return cleaned[:48] or ("inst-" + hashlib.sha1(s.encode()).hexdigest()[:8])


def _plasticity(evidence: int) -> float:
    return max(P_MIN, 1.0 / (1.0 + P_K * evidence))


def _clip(x: float) -> float:
    return max(C_MIN, min(C_MAX, x))


def _target(r: float) -> float:
    """Map a reward in [-1, 1] to a confidence target in [C_MIN, C_MAX]."""
    r = max(-1.0, min(1.0, r))
    return C_MIN + (r + 1.0) / 2.0 * (C_MAX - C_MIN)


# --- jsonl-backed instinct stores ------------------------------------------
def _load(path: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("id"):
                out[rec["id"]] = rec
    return out


def _save(path: Path, store: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    tmp.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in store.values()), encoding="utf-8")
    tmp.replace(path)


def _proj_path() -> Path:
    return brain_dir() / "instincts.jsonl"


def _global_path() -> Path:
    return global_brain_dir() / "instincts.jsonl"


def _replay_path() -> Path:
    return brain_dir() / "replay.json"


# --- reservoir (experience replay) -----------------------------------------
def _reservoir_add(iid: str, r: float) -> None:
    p = _replay_path()
    data = {"seen": 0, "buf": []}
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    data["seen"] += 1
    buf = data["buf"]
    if len(buf) < REPLAY_CAP:
        buf.append([iid, r])
    else:  # classic reservoir sampling — every sample equally likely to survive
        j = _rng.randint(0, data["seen"] - 1)
        if j < REPLAY_CAP:
            buf[j] = [iid, r]
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data), encoding="utf-8")


def _reservoir_sample(k: int) -> list[list]:
    p = _replay_path()
    if not p.exists():
        return []
    try:
        buf = json.loads(p.read_text(encoding="utf-8")).get("buf", [])
    except json.JSONDecodeError:
        return []
    if not buf:
        return []
    return [buf[_rng.randrange(len(buf))] for _ in range(min(k, len(buf)))]


# --- the RL update ----------------------------------------------------------
def _rl_update(inst: dict, r: float, *, factor: float = 1.0, count: bool = True) -> None:
    """Move confidence toward the reward target, scaled by plasticity. Live
    rewards (count=True) add evidence and re-consolidate; replay nudges don't."""
    target = _target(r)
    inst["confidence"] = _clip(inst["confidence"] + inst["plasticity"] * ALPHA * factor * (target - inst["confidence"]))
    if count:
        inst["evidence"] = int(inst.get("evidence", 1)) + 1
        inst["reward_sum"] = round(float(inst.get("reward_sum", 0.0)) + r, 4)
        inst["plasticity"] = round(_plasticity(inst["evidence"]), 4)
    inst["confidence"] = round(inst["confidence"], 4)
    inst["last_seen"] = _today()


def _replay_into(proj: dict[str, dict]) -> None:
    """Rehearse old samples so learning something new doesn't wipe the old."""
    for iid, r in _reservoir_sample(REPLAY_K):
        if iid in proj:
            _rl_update(proj[iid], float(r), factor=REPLAY_FACTOR, count=False)


# --- global tier (cross-project) -------------------------------------------
def _touch_global(iid: str, domain: str, pattern: str, conf: float) -> None:
    with lock(_global_path()):   # serialize the shared cross-project tier
        g = _load(_global_path())
        gi = g.get(iid) or {"id": iid, "domain": domain, "pattern": pattern,
                            "confidence": conf, "projects": [], "promoted": False}
        pid = _project_id()
        if pid not in gi["projects"]:
            gi["projects"] = sorted(set(gi["projects"] + [pid]))
        gi["confidence"] = round(max(gi["confidence"], conf), 4)
        gi["promoted"] = len(gi["projects"]) >= PROMOTE_PROJECTS
        gi["last_seen"] = _today()
        g[iid] = gi
        _save(_global_path(), g)


# --- commands ---------------------------------------------------------------
def cmd_observe(domain: str, pattern: str, iid: str | None) -> int:
    iid = iid or _slug(pattern)
    proj = _load(_proj_path())
    inst = proj.get(iid)
    if inst is None:
        inst = {"id": iid, "domain": domain, "pattern": pattern, "scope": "project",
                "confidence": C_INIT, "evidence": 1, "reward_sum": 0.0,
                "plasticity": round(_plasticity(1), 4), "created": _today(), "last_seen": _today()}
    else:
        inst["pattern"] = pattern
        inst["domain"] = domain
        inst["last_seen"] = _today()
    proj[iid] = inst
    _save(_proj_path(), proj)
    _touch_global(iid, domain, pattern, inst["confidence"])
    print(iid)
    return 0


def cmd_reward(iid: str, r: float) -> int:
    proj = _load(_proj_path())
    inst = proj.get(iid)
    if inst is None:
        print(f"unknown instinct: {iid} (observe it first)", file=sys.stderr)
        return 1
    _rl_update(inst, r, count=True)
    _reservoir_add(iid, r)
    _replay_into(proj)
    _save(_proj_path(), proj)
    _touch_global(iid, inst["domain"], inst["pattern"], inst["confidence"])
    print(inst["confidence"])
    return 0


def _relevant(domain: str) -> list[dict]:
    proj = _load(_proj_path())
    merged = dict(proj)
    for iid, gi in _load(_global_path()).items():
        if gi.get("promoted") and iid not in merged:  # project overrides global
            merged[iid] = {**gi, "scope": "global"}
    items = [i for i in merged.values() if i.get("domain") == domain]
    items.sort(key=lambda i: i.get("confidence", 0), reverse=True)
    return items


def cmd_simulate(domain: str, context: str, as_json: bool) -> int:
    items = _relevant(domain)
    top = items[0] if items else None
    if as_json:
        print(json.dumps(top or {}))
        return 0
    if not top:
        print(f"(no instinct for domain '{domain}' — decide on first principles)")
        return 0
    print(f"likely choice [{top['confidence']:.2f}]: {top['pattern']}")
    return 0


def cmd_recall(domain: str, as_json: bool) -> int:
    items = _relevant(domain)
    if as_json:
        print(json.dumps(items))
        return 0
    if not items:
        print(f"(nothing learned for domain '{domain}')")
        return 0
    for i in items:
        print(f"  [{i['confidence']:.2f}] ({i.get('scope', 'project')}) {i['pattern']}")
    return 0


def cmd_decay() -> int:
    proj = _load(_proj_path())
    for inst in proj.values():
        gap = inst["confidence"] - C_FLOOR
        if gap > 0:  # consolidated (low-plasticity) instincts shed far less
            inst["confidence"] = round(max(C_FLOOR, inst["confidence"] - inst["plasticity"] * DECAY_RATE * gap), 4)
    _save(_proj_path(), proj)
    print(f"decayed {len(proj)} instinct(s)")
    return 0


def cmd_promote() -> int:
    g = _load(_global_path())
    n = 0
    for gi in g.values():
        was = gi.get("promoted", False)
        gi["promoted"] = len(gi.get("projects", [])) >= PROMOTE_PROJECTS
        n += int(gi["promoted"] and not was)
    _save(_global_path(), g)
    promoted = sum(1 for gi in g.values() if gi.get("promoted"))
    print(f"{promoted} promoted ({n} newly)")
    return 0


def cmd_status(as_json: bool) -> int:
    proj = _load(_proj_path())
    glob = {k: v for k, v in _load(_global_path()).items() if v.get("promoted")}
    if as_json:
        print(json.dumps({"project": list(proj.values()), "global": list(glob.values())}))
        return 0
    print(f"second brain — {len(proj)} project instinct(s), {len(glob)} promoted global")
    for inst in sorted(proj.values(), key=lambda i: i.get("confidence", 0), reverse=True)[:20]:
        bar = "█" * round(inst["confidence"] * 10)
        print(f"  {inst['confidence']:.2f} {bar:<10} {inst['domain']:<14} {inst['pattern']}")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="brain.py")
    sub = ap.add_subparsers(dest="cmd")
    o = sub.add_parser("observe")
    o.add_argument("--domain", required=True)
    o.add_argument("--pattern", required=True)
    o.add_argument("--id", default=None)
    rw = sub.add_parser("reward")
    rw.add_argument("id")
    rw.add_argument("r", type=float)
    si = sub.add_parser("simulate")
    si.add_argument("--domain", required=True)
    si.add_argument("--context", default="")
    si.add_argument("--json", action="store_true")
    rc = sub.add_parser("recall")
    rc.add_argument("--domain", required=True)
    rc.add_argument("--json", action="store_true")
    sub.add_parser("decay")
    sub.add_parser("promote")
    st = sub.add_parser("status")
    st.add_argument("--json", action="store_true")
    args = ap.parse_args(argv[1:])

    if args.cmd == "observe":
        return cmd_observe(args.domain, args.pattern, args.id)
    if args.cmd == "reward":
        return cmd_reward(args.id, args.r)
    if args.cmd == "simulate":
        return cmd_simulate(args.domain, args.context, args.json)
    if args.cmd == "recall":
        return cmd_recall(args.domain, args.json)
    if args.cmd == "decay":
        return cmd_decay()
    if args.cmd == "promote":
        return cmd_promote()
    if args.cmd == "status":
        return cmd_status(args.json)
    ap.print_help(sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
