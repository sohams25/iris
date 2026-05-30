#!/usr/bin/env python3
"""Memory backend — CLI and library, all in one file.

Two backends:
  * markdown — handovers/handover_NNN.md (default; delegates create to
               scripts/handover-new.py to preserve continuity-engine output).
  * obsidian — notes inside an obsidian vault at $OBSIDIAN_VAULT.

Subcommands:
    current  [--id-only] [--json]
    list     [--json] [--limit N]
    create   [--title TITLE] [--reason REASON]    # stdout: new id only
    search   QUERY [--limit N] [--json]
    validate [--json]
    event    KIND --payload JSON

Exit codes:
    0  success (or "nothing to report" — `current` prints empty when no handover)
    1  bad args or backend failure
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Protocol

def _resolve_repo_root() -> Path:
    """The 'repo root' is the consuming project, not iris itself.

    Resolution order:
      1. $IRIS_ROOT — explicit override (tests, embedded installs)
      2. current working directory — the project Claude Code is open in

    The result is the directory under which `handovers/` (for the
    markdown backend) and `.iris-state/` (for the event log + run lock)
    live.
    """
    explicit = os.environ.get("IRIS_ROOT", "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()
    return Path.cwd().resolve()


REPO_ROOT = _resolve_repo_root()
HANDOVERS_DIR = REPO_ROOT / "handovers"
SCRIPTS_DIR = Path(__file__).resolve().parent
STATE_DIR = REPO_ROOT / ".iris-state"
ENV_FILE = REPO_ROOT / ".env"
HANDOVER_NEW = SCRIPTS_DIR / "handover-new.py"
HANDOVER_VALIDATE = SCRIPTS_DIR / "handover-validate.py"

HANDOVER_RE = re.compile(r"^handover_(\d{3})\.md$")
NOTE_RE = re.compile(r"^(?P<date>\d{4}-\d{2}-\d{2})__(?P<slug>.+?)(?:-(?P<n>\d+))?\.md$")


# ============================================================================
# Env loading
# ============================================================================

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


_ENV = _load_env()


def env(key: str, default: str = "") -> str:
    return os.environ.get(key) or _ENV.get(key, default)


# ============================================================================
# Handover dataclass + frontmatter helpers
# ============================================================================

@dataclass
class Handover:
    id: str
    title: str
    date: str
    status: str
    prev: str | None = None
    next: str | None = None
    body: str = ""
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


def _split_fm(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    try:
        import yaml
        fm = yaml.safe_load(parts[1]) or {}
    except ImportError:
        # Last-resort: stub parser for `key: value` lines
        fm = {}
        for line in parts[1].splitlines():
            if ":" in line and not line.startswith("-"):
                k, _, v = line.partition(":")
                fm[k.strip()] = v.strip().strip('"').strip("'") or None
    return fm, parts[2]


def _dump_fm(fm: dict[str, Any], body: str) -> str:
    import yaml
    return "---\n" + yaml.safe_dump(fm, sort_keys=False, allow_unicode=True) + "---\n" + body


# ============================================================================
# Backend protocol
# ============================================================================

class Memory(Protocol):
    backend_name: str
    def current_handover(self) -> Handover | None: ...
    def current_handover_id(self) -> str | None: ...
    def list_handovers(self) -> list[Handover]: ...
    def create_handover(self, title: str = "", reason: str = "manual") -> Handover: ...
    def append_event(self, kind: str, payload: dict[str, Any]) -> None: ...
    def validate(self) -> dict[str, Any]: ...
    def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]: ...


# ============================================================================
# Markdown backend — handovers/handover_NNN.md
# ============================================================================

class MarkdownMemory:
    backend_name = "markdown"

    def __init__(self, dir_: Path | None = None) -> None:
        self.dir = dir_ or HANDOVERS_DIR
        self.dir.mkdir(parents=True, exist_ok=True)

    def _all_paths(self) -> list[Path]:
        return [p for p in sorted(self.dir.glob("handover_*.md")) if HANDOVER_RE.match(p.name)]

    def _load(self, p: Path) -> Handover:
        text = p.read_text(encoding="utf-8")
        fm, body = _split_fm(text)
        return Handover(
            id=p.name,
            title=fm.get("title") or "",
            date=str(fm.get("date") or ""),
            status=fm.get("status") or "",
            prev=fm.get("prev"),
            next=fm.get("next"),
            body=body,
            tags=list(fm.get("tags") or []),
            metadata={"session_id": fm.get("session_id"), "source": fm.get("source")},
        )

    def current_handover(self) -> Handover | None:
        candidates = [self._load(p) for p in self._all_paths()]
        for h in candidates:
            if h.status == "current":
                return h
        return candidates[-1] if candidates else None

    def current_handover_id(self) -> str | None:
        h = self.current_handover()
        return h.id if h else None

    def list_handovers(self) -> list[Handover]:
        return sorted((self._load(p) for p in self._all_paths()), key=lambda h: h.id, reverse=True)

    def create_handover(self, title: str = "", reason: str = "manual") -> Handover:
        full_title = title or f"Checkpoint ({reason})"
        try:
            subprocess.run(
                ["python3", str(HANDOVER_NEW), "--title", full_title],
                cwd=str(REPO_ROOT), capture_output=True, text=True, check=True, timeout=30,
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"handover-new.py failed: {e.stderr or e.stdout}") from e
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(f"handover-new.py timed out after 30s: {e}") from e
        h = self.current_handover()
        if not h:
            raise RuntimeError("handover-new.py succeeded but no current handover found")
        h.metadata = {**h.metadata, "reason": reason}
        return h

    def append_event(self, kind: str, payload: dict[str, Any]) -> None:
        STATE_DIR.mkdir(exist_ok=True)
        events = STATE_DIR / "events.jsonl"
        # Order matters: payload first, then kind+ts so the positional kind
        # and the server-side ts win over any same-named keys in payload.
        record = {**payload, "kind": kind, "ts": datetime.now().isoformat()}
        with events.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    def validate(self) -> dict[str, Any]:
        try:
            res = subprocess.run(
                ["python3", str(HANDOVER_VALIDATE)],
                cwd=str(REPO_ROOT), capture_output=True, text=True, check=False, timeout=10,
            )
        except subprocess.SubprocessError as e:
            return {"checked": 0, "issues": [str(e)]}
        issues: list[str] = []
        checked = 0
        for line in res.stdout.splitlines():
            ls = line.strip()
            if ls.startswith("• "):
                issues.append(ls[2:])
            elif line.startswith("checked:"):
                try:
                    checked = int(line.split(":", 1)[1].strip().split()[0])
                except (ValueError, IndexError):
                    pass
        return {"checked": checked, "issues": issues}

    def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        q = query.lower()
        hits: list[dict[str, Any]] = []
        for p in self._all_paths():
            try:
                text = p.read_text(encoding="utf-8")
            except OSError:
                continue
            if q in text.lower():
                idx = text.lower().find(q)
                snippet = text[max(0, idx - 60): idx + 140].replace("\n", " ").strip()
                hits.append({"id": p.name, "snippet": snippet})
                if len(hits) >= limit:
                    break
        return hits


# ============================================================================
# Obsidian backend — vault at $OBSIDIAN_VAULT
# ============================================================================

def _slugify(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9\s-]", "", s).strip().lower()
    s = re.sub(r"[\s_]+", "-", s)
    return s[:50] or "checkpoint"


class ObsidianMemory:
    backend_name = "obsidian"

    def __init__(self, vault: Path | None = None) -> None:
        vault_env = env("OBSIDIAN_VAULT", "")
        if vault is None and not vault_env:
            raise RuntimeError(
                "MEMORY_BACKEND=obsidian requires OBSIDIAN_VAULT to be set "
                "(absolute path to an existing obsidian vault). "
                "Either export OBSIDIAN_VAULT=/path/to/vault, or set "
                "MEMORY_BACKEND=markdown to use the file-system fallback."
            )
        self.vault = vault or Path(vault_env).expanduser()
        if not self.vault.exists():
            raise RuntimeError(
                f"Obsidian vault not found at {self.vault}. "
                "Create the vault (or point OBSIDIAN_VAULT at an existing "
                "one), or fall back to MEMORY_BACKEND=markdown."
            )
        # Obsidian vault layout: work/handovers for session checkpoints
        # (parallel to handovers/ on the markdown backend), and a JSONL
        # event log under perf/.
        self.work = self.vault / "work" / "handovers"
        self.work.mkdir(parents=True, exist_ok=True)
        self.events = self.vault / "perf" / "workspace-events.jsonl"
        self.events.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _sort_key(p: Path) -> tuple[str, str, int]:
        """Sort key that respects the optional `-<N>` collision suffix.

        Bare lex sort breaks here because `'-'` (0x2D) < `'.'` (0x2E), so a
        same-day file `<date>__foo-2.md` would lex-sort BEFORE its base
        `<date>__foo.md`. With this key the base counts as N=0 and the
        suffixed siblings sort after, preserving creation order.
        """
        m = NOTE_RE.match(p.name)
        if not m:
            return (p.name, "", 0)
        return (m.group("date"), m.group("slug"), int(m.group("n") or 0))

    def _all_paths(self) -> list[Path]:
        return sorted(
            [p for p in self.work.glob("*.md") if NOTE_RE.match(p.name)],
            key=self._sort_key,
        )

    def _load(self, p: Path) -> Handover:
        text = p.read_text(encoding="utf-8")
        fm, body = _split_fm(text)
        m = NOTE_RE.match(p.name)
        return Handover(
            id=p.name,
            title=fm.get("title") or "",
            date=str(fm.get("date") or (m.group("date") if m else "")),
            status=fm.get("status") or "",
            prev=fm.get("prev"),
            next=fm.get("next"),
            body=body,
            tags=list(fm.get("tags") or []),
            metadata={"reason": fm.get("reason"), "session_id": fm.get("session_id")},
        )

    def current_handover(self) -> Handover | None:
        paths = self._all_paths()
        if not paths:
            return None
        items = [self._load(p) for p in paths]
        for h in items:
            if h.status == "current":
                return h
        return items[-1]

    def current_handover_id(self) -> str | None:
        h = self.current_handover()
        return h.id if h else None

    def list_handovers(self) -> list[Handover]:
        # _all_paths() returns chronological (oldest → newest) via _sort_key.
        # We want newest first, so just reverse — don't re-sort by raw h.id
        # which would scramble same-day -N suffix ordering (HIGH bug from
        # /code-review: '-' < '.' in ASCII).
        return [self._load(p) for p in reversed(self._all_paths())]

    def create_handover(self, title: str = "", reason: str = "manual") -> Handover:
        today = date.today().isoformat()
        slug = _slugify(title or reason)
        path = self.work / f"{today}__{slug}.md"
        n = 1
        while path.exists():
            n += 1
            path = self.work / f"{today}__{slug}-{n}.md"

        prev = self.current_handover()
        carry_standing = ""
        carry_next = ""
        if prev:
            for section, key in (("Standing instructions", "_s"), ("Next session", "_n")):
                m = re.search(
                    rf"##\s+\d*\.?\s*{re.escape(section)}.*?\n(.*?)(?=\n##\s|\Z)",
                    prev.body, re.IGNORECASE | re.DOTALL,
                )
                if m:
                    if key == "_s":
                        carry_standing = m.group(1).strip()
                    else:
                        carry_next = m.group(1).strip()

        fm = {
            "date": today,
            "title": title or f"Checkpoint ({reason})",
            "status": "current",
            "tags": ["iris", "handover", reason],
            "prev": f"[[{prev.id.removesuffix('.md')}]]" if prev else None,
            "next": None,
            "reason": reason,
            "source": "iris",
        }
        body = f"""

# {fm['title']}

## 0. Standing instructions (carried forward)

{carry_standing or "_(none from prior)_"}

## 1. Branch state

_(populate during the session)_

## 2. What changed this session

_(populate during the session)_

## 3. Open threads carried forward

{carry_next or "_(none from prior)_"}

## 7. Next session — start here

_(write specific next steps here)_
"""
        path.write_text(_dump_fm(fm, body), encoding="utf-8")

        if prev:
            prev_path = self.work / prev.id
            prev_text = prev_path.read_text(encoding="utf-8")
            prev_fm, prev_body = _split_fm(prev_text)
            prev_fm["status"] = "superseded"
            prev_fm["next"] = f"[[{path.name.removesuffix('.md')}]]"
            prev_path.write_text(_dump_fm(prev_fm, prev_body), encoding="utf-8")

        return Handover(
            id=path.name, title=fm["title"], date=today, status="current",
            prev=prev.id if prev else None, next=None, body=body,
            tags=fm["tags"],
            metadata={"reason": reason, "prev_updated": prev.id if prev else None},
        )

    def append_event(self, kind: str, payload: dict[str, Any]) -> None:
        # Order matters: payload first, then kind+ts so positional args win.
        record = {**payload, "kind": kind, "ts": datetime.now().isoformat()}
        with self.events.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    def validate(self) -> dict[str, Any]:
        items = self.list_handovers()
        issues: list[str] = []
        currents = [h for h in items if h.status == "current"]
        if len(currents) > 1:
            issues.append(f"multiple status=current: {[h.id for h in currents]}")
        ids = {h.id for h in items}
        for h in items:
            if h.prev:
                key = h.prev.strip("[]")
                # Accept both bare-stem and explicit `.md` link targets.
                if not ((key + ".md") in ids or key in ids):
                    issues.append(f"{h.id}: prev={h.prev} missing")
        return {"checked": len(items), "issues": issues}

    def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        q = query.lower()
        hits: list[dict[str, Any]] = []
        for p in self._all_paths():
            try:
                text = p.read_text(encoding="utf-8")
            except OSError:
                continue
            if q in text.lower():
                idx = text.lower().find(q)
                snippet = text[max(0, idx - 60): idx + 140].replace("\n", " ").strip()
                hits.append({"id": p.name, "snippet": snippet})
                if len(hits) >= limit:
                    break
        return hits


# ============================================================================
# Factory
# ============================================================================

def get_memory() -> Memory:
    backend = (env("MEMORY_BACKEND", "markdown") or "markdown").lower().strip()
    if backend == "obsidian":
        return ObsidianMemory()
    if backend == "markdown":
        return MarkdownMemory()
    raise ValueError(f"Unknown MEMORY_BACKEND: {backend}")


# ============================================================================
# CLI subcommands
# ============================================================================

def cmd_current(args: argparse.Namespace) -> int:
    try:
        h = get_memory().current_handover()
    except Exception as e:  # noqa: BLE001
        print(f"memory backend error: {e}", file=sys.stderr)
        return 1
    if not h:
        return 0  # empty stdout, exit 0 — hooks rely on this
    if args.id_only:
        print(h.id)
        return 0
    if args.json:
        print(json.dumps({
            "id": h.id, "title": h.title, "date": h.date,
            "status": h.status, "prev": h.prev, "next": h.next,
            "tags": list(h.tags), "body": h.body,
        }, indent=2))
        return 0
    print(f"id:      {h.id}")
    print(f"title:   {h.title}")
    print(f"date:    {h.date}")
    print(f"status:  {h.status}")
    print(f"prev:    {h.prev or '-'}")
    print(f"next:    {h.next or '-'}")
    print(f"tags:    {', '.join(h.tags) if h.tags else '-'}")
    print()
    print(h.body)
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    try:
        items = get_memory().list_handovers()
    except Exception as e:  # noqa: BLE001
        print(f"memory backend error: {e}", file=sys.stderr)
        return 1
    items = items[: args.limit]
    if args.json:
        print(json.dumps([{
            "id": h.id, "title": h.title, "date": h.date,
            "status": h.status, "prev": h.prev, "next": h.next,
            "tags": list(h.tags),
        } for h in items], indent=2))
        return 0
    for h in items:
        marker = "*" if h.status == "current" else " "
        print(f"  {marker} {h.id:24s} {h.date or '?':10s} {h.title or '(untitled)'}")
    return 0


def cmd_create(args: argparse.Namespace) -> int:
    try:
        h = get_memory().create_handover(title=args.title or "", reason=args.reason)
    except Exception as e:  # noqa: BLE001
        print(f"create failed: {e}", file=sys.stderr)
        return 1
    print(f"created: handovers/{h.id}", file=sys.stderr)
    prev = h.metadata.get("prev_updated") if h.metadata else None
    if prev:
        print(f"updated: handovers/{prev} (status=superseded)", file=sys.stderr)
    print(h.id)
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    if not args.query:
        print("usage: memory.py search QUERY", file=sys.stderr)
        return 1
    try:
        hits = get_memory().search(args.query, limit=args.limit)
    except Exception as e:  # noqa: BLE001
        print(f"search failed: {e}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(hits, indent=2))
        return 0
    if not hits:
        print("(no hits)")
        return 0
    for h in hits:
        print(f"  * {h.get('id', '?'):24s} — {h.get('snippet', '').strip()}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    try:
        rep = get_memory().validate()
    except Exception as e:  # noqa: BLE001
        print(f"validate failed: {e}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(rep, indent=2))
        return 0
    checked = rep.get("checked", "?")
    issues = rep.get("issues") or []
    if not issues:
        print(f"checked: {checked} handovers; no issues.")
        return 0
    print(f"checked: {checked} handovers")
    print(f"issues:  {len(issues)}")
    for i in issues:
        print(f"  • {i}")
    return 0


def cmd_event(args: argparse.Namespace) -> int:
    try:
        payload = json.loads(args.payload or "{}")
    except json.JSONDecodeError as e:
        print(f"bad --payload JSON: {e}", file=sys.stderr)
        return 1
    try:
        get_memory().append_event(args.kind, payload)
    except Exception as e:  # noqa: BLE001
        print(f"event append failed: {e}", file=sys.stderr)
        return 1
    return 0


# ============================================================================
# Argparse + entrypoint
# ============================================================================

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="memory.py")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("current")
    sp.add_argument("--id-only", action="store_true")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_current)

    sp = sub.add_parser("list")
    sp.add_argument("--json", action="store_true")
    sp.add_argument("--limit", type=int, default=20)
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("create")
    sp.add_argument("--title", default="")
    sp.add_argument("--reason", default="manual")
    sp.set_defaults(func=cmd_create)

    sp = sub.add_parser("search")
    sp.add_argument("query", nargs="?", default="")
    sp.add_argument("--limit", type=int, default=20)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_search)

    sp = sub.add_parser("validate")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_validate)

    sp = sub.add_parser("event")
    sp.add_argument("kind")
    sp.add_argument("--payload", default="{}")
    sp.set_defaults(func=cmd_event)

    args = p.parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
