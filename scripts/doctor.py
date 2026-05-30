#!/usr/bin/env python3
"""Health checks for an iris install.

14 checks. Used by the `/doctor` slash command and by the optional
Slack integration's `health()` method.

Exit codes:
    0  all checks pass
    1  one or more checks failed
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _iris_paths import plan_path, repo_root

REPO_ROOT = repo_root()


def _ok(detail: str) -> tuple[bool, str]:
    return True, detail


def _fail(detail: str) -> tuple[bool, str]:
    return False, detail


def check_claude_cli() -> tuple[bool, str]:
    p = shutil.which(os.environ.get("CLAUDE_BIN", "claude"))
    if not p:
        return _fail("claude CLI not in PATH")
    try:
        v = subprocess.run([p, "--version"], capture_output=True, text=True, timeout=5).stdout.strip()
        return _ok(f"{p} ({v or 'no version'})")
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        return _fail(f"{p}: {e}")


def check_plan_md() -> tuple[bool, str]:
    plan = plan_path()
    if not plan.exists():
        return _fail(f"{plan} missing")
    try:
        res = subprocess.run(
            ["python3", str(REPO_ROOT / "scripts" / "parse-tasks.py"), "list"],
            cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=5,
        )
        if res.returncode != 0:
            return _fail(f"parse-tasks.py list failed: {res.stderr.strip()[:120]}")
        json.loads(res.stdout)
        return _ok("docs/plan.md valid")
    except (subprocess.SubprocessError, json.JSONDecodeError) as e:
        return _fail(f"plan.md parse error: {e}")


def check_memory_current() -> tuple[bool, str]:
    try:
        res = subprocess.run(
            ["python3", str(REPO_ROOT / "scripts" / "memory.py"), "current", "--id-only"],
            cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=5,
        )
        if res.returncode != 0:
            return _fail(f"memory.py error: {res.stderr.strip()[:120]}")
        hid = res.stdout.strip()
        if not hid:
            return _ok("(no current handover — /rollover to create one)")
        return _ok(f"current: {hid}")
    except subprocess.SubprocessError as e:
        return _fail(str(e))


def check_memory_backend() -> tuple[bool, str]:
    # Report the configured backend by reading the env vars; the actual
    # backend constructor is exercised by check_memory_current() via
    # subprocess to scripts/memory.py, so we don't duplicate that work.
    backend = os.environ.get("MEMORY_BACKEND")
    if not backend:
        # Read .env file if env var not set
        env_file = REPO_ROOT / ".env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("MEMORY_BACKEND="):
                    backend = line.partition("=")[2].strip().strip('"').strip("'")
                    break
    backend = backend or "markdown"
    if backend not in {"markdown", "obsidian"}:
        return _fail(f"unknown MEMORY_BACKEND={backend} (expected markdown|obsidian)")
    return _ok(f"backend: {backend}")


def check_scripts_present() -> tuple[bool, str]:
    missing = []
    scripts = ("_iris_paths.py", "parse-tasks.py", "queue.py", "brain.py",
               "takeover.py", "notify.py", "notify-slack.sh", "handover-new.py",
               "handover-validate.py", "build-wave-plan.py", "detect-verify.sh",
               "memory.py")
    for s in scripts:
        if not (REPO_ROOT / "scripts" / s).exists():
            missing.append(s)
    if missing:
        return _fail(f"missing: {', '.join(missing)}")
    return _ok(f"all {len(scripts)} scripts present")


def check_hooks() -> tuple[bool, str]:
    hooks_dir = REPO_ROOT / ".claude" / "hooks"
    needed = [
        "session-start.sh",
        "pre-compact.sh",
        "block-ai-commit-trailers.sh",
    ]
    missing = [h for h in needed if not (hooks_dir / h).exists()]
    if missing:
        return _fail(f"missing: {', '.join(missing)}")
    non_exec = [h for h in needed if not os.access(hooks_dir / h, os.X_OK)]
    if non_exec:
        return _fail(f"not executable: {', '.join(non_exec)}")
    return _ok(f"{len(needed)}/{len(needed)} hooks ready")


def check_projects_dir() -> tuple[bool, str]:
    """Verify that the directory named by $PROJECTS_DIR exists.

    The plugin-portability story leans on this variable: a consumer
    renames it (e.g. PROJECTS_DIR=Projects) and the slash command
    /new-task scaffolds into the new location. If the target directory
    does not exist on disk, /new-task will create it on first use, but
    that masks typos. A doctor-level warning makes the misconfig visible
    at session start.
    """
    projects_dir = os.environ.get("PROJECTS_DIR")
    if not projects_dir:
        env_file = REPO_ROOT / ".env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("PROJECTS_DIR="):
                    projects_dir = line.partition("=")[2].strip().strip('"').strip("'")
                    break
    projects_dir = projects_dir or "Projects"
    p = REPO_ROOT / projects_dir
    if not p.exists():
        return _fail(f"{projects_dir}/ missing (PROJECTS_DIR={projects_dir})")
    if not p.is_dir():
        return _fail(f"{projects_dir} exists but is not a directory")
    return _ok(f"{projects_dir}/")


def check_settings_json() -> tuple[bool, str]:
    p = REPO_ROOT / ".claude" / "settings.json"
    if not p.exists():
        return _fail("missing")
    try:
        json.loads(p.read_text(encoding="utf-8"))
        return _ok("valid JSON")
    except json.JSONDecodeError as e:
        return _fail(f"invalid JSON: {e}")


def check_skill_symlinks() -> tuple[bool, str]:
    """Verify any symlinks under .claude/skills/ resolve to existing targets.

    Catches the case where ~/Tools/superpowers/ (or any other source) has been
    moved or deleted — the symlinks become dangling and Claude Code's skill
    loader silently fails on the affected skills.
    """
    skills_dir = REPO_ROOT / ".claude" / "skills"
    if not skills_dir.exists():
        return _ok("no .claude/skills/ (skip)")
    broken: list[str] = []
    total = 0
    for entry in skills_dir.iterdir():
        if not entry.is_symlink():
            continue
        total += 1
        target = entry.resolve(strict=False)
        if not target.exists():
            broken.append(f"{entry.name} → {target}")
    if broken:
        return _fail(f"broken symlinks ({len(broken)}/{total}): " + "; ".join(broken[:3]))
    return _ok(f"{total} symlinks all resolve")


def check_slash_commands() -> tuple[bool, str]:
    cmds_dir = REPO_ROOT / ".claude" / "commands"
    needed = ["submit.md", "run.md", "status.md", "backlog.md", "rollover.md",
              "memory.md", "doctor.md", "new-task.md", "takeover.md"]
    missing = [c for c in needed if not (cmds_dir / c).exists()]
    if missing:
        return _fail(f"missing: {', '.join(missing)}")
    return _ok(f"{len(needed)}/{len(needed)} commands present")


def check_slack_config() -> tuple[bool, str]:
    env_file = REPO_ROOT / ".env"
    if not env_file.exists():
        return _ok("not configured (no .env; optional integration)")
    text = env_file.read_text(encoding="utf-8")
    set_vars = []
    for var in ("SLACK_BOT_TOKEN", "SLACK_APP_TOKEN", "SLACK_CHANNEL_ID", "SLACK_WEBHOOK_URL"):
        for line in text.splitlines():
            if line.startswith(f"{var}=") and line.split("=", 1)[1].strip():
                set_vars.append(var)
                break
    if not set_vars:
        # Slack is one of several optional integrations in iris (it was
        # mandatory in the originating workspace). An unconfigured adapter is
        # not a health failure — surface it as informational so a fresh
        # install with no Slack creds still passes doctor.
        return _ok("not configured (optional integration)")
    return _ok(f"set: {', '.join(set_vars)}")


def check_detect_verify() -> tuple[bool, str]:
    try:
        res = subprocess.run(
            ["bash", str(REPO_ROOT / "scripts" / "detect-verify.sh")],
            cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=5,
        )
        out = res.stdout.strip()
        if not out or "no verify command configured" in out:
            return _ok(f"fallback: {out or 'true'}")
        return _ok(out[:60])
    except subprocess.SubprocessError as e:
        return _fail(str(e))


def check_git() -> tuple[bool, str]:
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=5,
        )
        if res.returncode != 0:
            return _fail("not a git working tree")
        return _ok(f"branch: {res.stdout.strip()}")
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        return _fail(str(e))


def check_claude_md() -> tuple[bool, str]:
    p = REPO_ROOT / "CLAUDE.md"
    if not p.exists():
        return _fail("CLAUDE.md missing at repo root (auto-loaded project context)")
    return _ok(f"{p.stat().st_size} bytes")


CHECKS = [
    ("claude CLI", check_claude_cli),
    ("docs/plan.md", check_plan_md),
    ("memory current", check_memory_current),
    ("memory backend", check_memory_backend),
    ("scripts/", check_scripts_present),
    ("hooks", check_hooks),
    ("settings.json", check_settings_json),
    ("slash commands", check_slash_commands),
    ("skill symlinks", check_skill_symlinks),
    ("CLAUDE.md", check_claude_md),
    ("slack config", check_slack_config),
    ("projects dir", check_projects_dir),
    ("verify cmd", check_detect_verify),
    ("git", check_git),
]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="doctor.py")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    results = []
    for name, fn in CHECKS:
        try:
            ok, detail = fn()
        except Exception as e:  # noqa: BLE001
            ok, detail = False, f"check raised: {e}"
        results.append({"name": name, "ok": ok, "detail": detail})

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(f"doctor — {sum(r['ok'] for r in results)}/{len(results)} checks pass")
        print("-" * 60)
        for r in results:
            mark = "✓" if r["ok"] else "✗"
            print(f"  {mark}  {r['name']:20s} {r['detail']}")
    return 0 if all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
