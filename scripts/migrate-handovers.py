#!/usr/bin/env python3
"""One-shot migration: handovers/handover_NNN.md  →  $OBSIDIAN_VAULT/work/handovers/

For each markdown handover at handovers/handover_NNN.md, emit an
obsidian-format note at <vault>/work/handovers/<date>__<slug>.md preserving
the body byte-for-byte and re-encoding the front-matter to use [[wikilinks]]
for prev/next per the obsidian backend's convention.

  - 003, 004 → status: superseded
  - 005      → status: current

Refuses to overwrite existing notes. Refuses to run if the vault directory
does not exist. Refuses to clobber a non-empty work/handovers/ unless
--force is passed.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required (pip install --user pyyaml)", file=sys.stderr)
    sys.exit(1)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _iris_paths import repo_root, handovers_dir

REPO_ROOT = repo_root()
HANDOVERS_DIR = handovers_dir()
HANDOVER_RE = re.compile(r"^handover_(\d{3})\.md$")


def _slugify(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9\s-]", "", s).strip().lower()
    s = re.sub(r"[\s_]+", "-", s)
    return s[:50] or "checkpoint"


def _split_fm(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    return yaml.safe_load(parts[1]) or {}, parts[2]


def _dump_fm(fm: dict, body: str) -> str:
    return "---\n" + yaml.safe_dump(fm, sort_keys=False, allow_unicode=True) + "---" + body


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--vault", help="override OBSIDIAN_VAULT")
    ap.add_argument("--force", action="store_true",
                    help="proceed even if work/handovers/ already contains notes "
                         "(per-file overwrite is still refused; use --replace to clobber)")
    ap.add_argument("--replace", action="store_true",
                    help="overwrite any existing notes whose names match a planned write "
                         "(implies --force)")
    ap.add_argument("--dry-run", action="store_true", help="print planned writes without modifying anything")
    args = ap.parse_args(argv)

    vault_arg = args.vault
    if not vault_arg:
        env_file = REPO_ROOT / ".env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("OBSIDIAN_VAULT="):
                    vault_arg = line.partition("=")[2].strip().strip('"').strip("'")
                    break
    if not vault_arg:
        print("OBSIDIAN_VAULT not set in env or .env", file=sys.stderr)
        return 1
    vault = Path(vault_arg).expanduser()
    if not vault.exists():
        print(f"vault does not exist: {vault}", file=sys.stderr)
        return 1
    work = vault / "work" / "handovers"
    work.mkdir(parents=True, exist_ok=True)

    if args.replace:
        args.force = True

    existing = [p for p in work.glob("*.md") if not p.name.startswith(".")]
    if existing and not args.force:
        print(
            f"{work} already contains {len(existing)} note(s). "
            "Use --force to proceed alongside them, or --replace to clobber matching names.",
            file=sys.stderr,
        )
        return 1

    if not HANDOVERS_DIR.exists():
        print(f"source handovers/ missing: {HANDOVERS_DIR}", file=sys.stderr)
        return 1

    sources = sorted(p for p in HANDOVERS_DIR.glob("handover_*.md") if HANDOVER_RE.match(p.name))
    if not sources:
        print("no handover_NNN.md files to migrate", file=sys.stderr)
        return 0

    # First pass: parse each source, compute the new filename, build an in-order list
    plans: list[dict] = []
    for src in sources:
        m = HANDOVER_RE.match(src.name)
        num = int(m.group(1))
        text = src.read_text(encoding="utf-8")
        fm, body = _split_fm(text)
        date = str(fm.get("date") or "1970-01-01")
        title = str(fm.get("title") or f"Handover {num:03d}")
        slug = _slugify(title)
        new_name = f"{date}__{slug}.md"
        plans.append({
            "num": num,
            "src": src,
            "new_name": new_name,
            "fm": fm,
            "body": body,
            "is_last": False,
        })
    plans[-1]["is_last"] = True

    # Pre-flight uniqueness check — if two sources produce the same target
    # filename (same date AND same slug), we must abort BEFORE any writes.
    # Otherwise the first write succeeds, the second aborts on the per-file
    # guard, and the vault is left with a broken prev/next chain.
    seen: dict[str, int] = {}
    for plan in plans:
        seen[plan["new_name"]] = seen.get(plan["new_name"], 0) + 1
    collisions = [name for name, count in seen.items() if count > 1]
    if collisions:
        print(
            "aborting: two or more handovers would map to the same vault "
            "filename. Disambiguate the titles in the source markdown and retry.\n"
            "  collisions: " + ", ".join(collisions),
            file=sys.stderr,
        )
        return 1

    # Second pass: emit each note with prev/next as [[wikilinks]]
    for i, plan in enumerate(plans):
        prev_name = plans[i - 1]["new_name"] if i > 0 else None
        next_name = plans[i + 1]["new_name"] if i < len(plans) - 1 else None
        status = "current" if plan["is_last"] else "superseded"

        new_fm = {
            "date": plan["fm"].get("date"),
            "title": plan["fm"].get("title"),
            "session_id": plan["fm"].get("session_id"),
            "prev": f"[[{prev_name.removesuffix('.md')}]]" if prev_name else None,
            "next": f"[[{next_name.removesuffix('.md')}]]" if next_name else None,
            "status": status,
            "tags": plan["fm"].get("tags") or [],
            "reason": "migrated-from-markdown",
            "source": plan["fm"].get("source") or f"handovers/{plan['src'].name}",
        }
        dest = work / plan["new_name"]
        if dest.exists() and not args.replace:
            print(
                f"refusing to overwrite existing: {dest} "
                "(pass --replace to overwrite matching filenames)",
                file=sys.stderr,
            )
            return 1

        if args.dry_run:
            print(f"[dry-run] would write {dest} (status={status}, prev={prev_name}, next={next_name})")
            continue

        dest.write_text(_dump_fm(new_fm, plan["body"]), encoding="utf-8")
        print(f"migrated: {plan['src']} → {dest}", file=sys.stderr)
        print(plan["new_name"])

    return 0


if __name__ == "__main__":
    sys.exit(main())
