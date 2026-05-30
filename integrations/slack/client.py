"""Backend client — shells out to iris's scripts/*.py and parses the result.

Every method invokes a script under scripts/ (parse-tasks, memory, doctor,
build-wave-plan) with the consumer project as the working directory, so the
Slack bot drives the same backend a local Claude Code session does.

Long-running "run" semantics spawn a headless `claude -p "/run"` session
with --dangerously-skip-permissions, supervised via .iris-state/run.lock.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))
from _iris_paths import repo_root

REPO_ROOT = repo_root()
SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
PARSE_TASKS = SCRIPTS_DIR / "parse-tasks.py"
MEMORY = SCRIPTS_DIR / "memory.py"
DOCTOR = SCRIPTS_DIR / "doctor.py"
BUILD_WAVE = SCRIPTS_DIR / "build-wave-plan.py"
RUN_LOCK = REPO_ROOT / ".iris-state" / "run.lock"
CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "claude")


class BackendError(Exception):
    pass


def _script(name: Path, *args: str, timeout: int = 30, check: bool = True) -> subprocess.CompletedProcess:
    """Run a Python script under scripts/. Raise BackendError on failure if check=True."""
    cmd = ["python3", str(name), *args]
    try:
        res = subprocess.run(
            cmd, cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=timeout,
        )
    except FileNotFoundError as e:
        raise BackendError(f"{name.name} not found: {e}") from e
    except subprocess.TimeoutExpired as e:
        raise BackendError(f"{name.name} timed out after {timeout}s") from e
    if check and res.returncode != 0:
        raise BackendError(f"{name.name} → rc={res.returncode}: {(res.stderr or res.stdout).strip()[:400]}")
    return res


def _read_lock_pid() -> int | None:
    if not RUN_LOCK.exists():
        return None
    try:
        return int(RUN_LOCK.read_text().strip())
    except (OSError, ValueError):
        return None


def _is_pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


# ---------- Health ----------

def health() -> bool:
    """Are all doctor checks green?"""
    try:
        res = _script(DOCTOR, "--json", timeout=10, check=False)
        return res.returncode == 0
    except BackendError:
        return False


# ---------- Plan ----------

def get_plan() -> dict[str, Any]:
    res = _script(PARSE_TASKS, "list", timeout=10)
    return {"tasks": json.loads(res.stdout or "[]")}


def add_task(task_id: str, title: str, files: list[str] | None = None,
             priority: int | None = None) -> dict[str, Any]:
    args = ["add", "--id", task_id, "--title", title]
    if priority is not None:
        args.extend(["--priority", str(priority)])
    if files:
        args.extend(["--files", ",".join(files)])
    res = _script(PARSE_TASKS, *args, timeout=15)
    out = res.stdout.strip()
    t: dict[str, Any] = {"id": task_id, "title": title}
    if files:
        t["files"] = files
    if priority is not None:
        t["priority"] = priority
    return {"task": t, "stdout": out}


def patch_task(task_id: str, **patch: Any) -> dict[str, Any]:
    for key, value in patch.items():
        v = value
        if isinstance(value, bool):
            v = "true" if value else "false"
        _script(PARSE_TASKS, "mark", task_id, key, str(v), timeout=10)
    return {"task_id": task_id, "patch": patch}


def delete_task(task_id: str) -> dict[str, Any]:
    raise BackendError("delete not supported via CLI yet — edit docs/plan.md directly")


# ---------- Run (headless claude -p "/run") ----------

def loop_status() -> dict[str, Any]:
    """Compose a status snapshot from the underlying scripts.

    Keys preserved for handler compatibility:
      running, pid, started_at, elapsed_seconds, exit_code, log_file, args,
      buffered_lines, tasks, memory, rollover
    """
    # Backlog
    try:
        plan = get_plan()
        tasks = plan.get("tasks", [])
        opens = sum(1 for t in tasks if not t.get("passes") and not t.get("blocked"))
        blocked = sum(1 for t in tasks if t.get("blocked"))
        done = sum(1 for t in tasks if t.get("passes"))
        next_open = next(
            (t for t in sorted(tasks, key=lambda x: (x.get("priority", 999), x.get("id", "")))
             if not t.get("passes") and not t.get("blocked")),
            None,
        )
    except BackendError:
        opens = blocked = done = 0
        next_open = None

    # Memory
    try:
        mres = _script(MEMORY, "current", "--id-only", timeout=5, check=False)
        current_handover = mres.stdout.strip() or None
    except BackendError:
        current_handover = None

    # Resolve MEMORY_BACKEND from os.environ first, then from .env at the repo
    # root (mirroring scripts/memory.py:_load_env), defaulting to markdown.
    backend_name = os.environ.get("MEMORY_BACKEND")
    if not backend_name:
        env_file = REPO_ROOT / ".env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("MEMORY_BACKEND="):
                    backend_name = line.partition("=")[2].strip().strip('"').strip("'")
                    break
    backend_name = backend_name or "markdown"

    # Run lock
    pid = _read_lock_pid()
    running = bool(pid and _is_pid_alive(pid))
    if pid and not running:
        # Stale lock — clean it up
        try:
            RUN_LOCK.unlink(missing_ok=True)
        except OSError:
            pass
        pid = None

    return {
        "running": running,
        "pid": pid,
        "started_at": None,
        "elapsed_seconds": None,
        "exit_code": None,
        "log_file": None,
        "args": [],
        "buffered_lines": 0,
        "tasks": {
            "open": opens,
            "blocked": blocked,
            "done": done,
            "next": next_open.get("id") if next_open else None,
            "next_title": next_open.get("title") if next_open else None,
        },
        "memory": {
            "backend": backend_name,
            "current": current_handover,
        },
        "rollover": {"handover": current_handover},
    }


def loop_start(max_iterations: int = 50, max_minutes: int = 480, dry_run: bool = False) -> dict[str, Any]:
    """Spawn a headless `claude -p "/run ..."` session in the background.

    The /run slash command (defined at .claude/commands/run.md) implements the
    loop semantics. We supervise via .iris-state/run.lock; lock creation is
    atomic via O_EXCL so concurrent Slack starts can't double-spawn.
    """
    RUN_LOCK.parent.mkdir(parents=True, exist_ok=True)

    # Reap a stale lock first (dead pid → safe to clear).
    pid = _read_lock_pid()
    if pid:
        if _is_pid_alive(pid):
            return {"started": False, "reason": f"already running (pid {pid})", "status": loop_status()}
        try:
            RUN_LOCK.unlink(missing_ok=True)
        except OSError:
            pass

    # Atomic lock creation. If a concurrent caller wins the race, we bail.
    try:
        lock_fd = os.open(str(RUN_LOCK), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        return {
            "started": False,
            "reason": "another start raced us to the lock",
            "status": loop_status(),
        }

    log = REPO_ROOT / ".iris-state" / f"run-bg-{int(time.time())}.log"
    log.parent.mkdir(parents=True, exist_ok=True)

    prompt = f"/run max_iterations={max_iterations} max_minutes={max_minutes}"
    if dry_run:
        prompt += " dry_run=true"

    args = [
        CLAUDE_BIN, "-p", prompt,
        "--dangerously-skip-permissions",
        "--output-format", "stream-json",
    ]
    try:
        with log.open("ab") as log_fp:
            try:
                proc = subprocess.Popen(
                    args, cwd=str(REPO_ROOT),
                    stdout=log_fp, stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            except (FileNotFoundError, OSError) as e:
                os.close(lock_fd)
                try:
                    RUN_LOCK.unlink(missing_ok=True)
                except OSError:
                    pass
                raise BackendError(f"claude CLI failed to start: {e}") from e

        os.write(lock_fd, str(proc.pid).encode())
        os.close(lock_fd)
    except BaseException:
        # If anything above failed after we acquired the lock, release it.
        try:
            os.close(lock_fd)
        except OSError:
            pass
        try:
            RUN_LOCK.unlink(missing_ok=True)
        except OSError:
            pass
        raise

    # Give claude a moment to boot, then verify it didn't immediately exit.
    time.sleep(0.4)
    if not _is_pid_alive(proc.pid):
        try:
            RUN_LOCK.unlink(missing_ok=True)
        except OSError:
            pass
        return {
            "started": False,
            "reason": f"claude exited immediately (rc={proc.poll()}). See {log}",
            "status": loop_status(),
        }

    return {
        "started": True,
        "status": {**loop_status(), "log_file": str(log), "pid": proc.pid},
    }


def loop_stop() -> dict[str, Any]:
    """SIGTERM the pid recorded in the run lock."""
    pid = _read_lock_pid()
    if not pid:
        return {"stopped": False, "exit_code": None, "detail": "no run lock"}
    if not _is_pid_alive(pid):
        try:
            RUN_LOCK.unlink(missing_ok=True)
        except OSError:
            pass
        return {"stopped": False, "exit_code": None, "detail": f"pid {pid} not alive (lock cleared)"}
    try:
        # Try the process group first (start_new_session=True at spawn), then the pid.
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        except ProcessLookupError:
            os.kill(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError) as e:
        return {"stopped": False, "exit_code": None, "detail": str(e)}
    # Give it a moment to die
    for _ in range(20):
        if not _is_pid_alive(pid):
            break
        time.sleep(0.1)
    try:
        RUN_LOCK.unlink(missing_ok=True)
    except OSError:
        pass
    return {"stopped": True, "exit_code": 0, "detail": f"SIGTERM sent to pid {pid}"}


# ---------- Git ----------

def git_status() -> dict[str, Any]:
    try:
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(REPO_ROOT), capture_output=True, text=True, check=True, timeout=5,
        ).stdout.strip()
        head = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(REPO_ROOT), capture_output=True, text=True, check=True, timeout=5,
        ).stdout.strip()
        short = subprocess.run(
            ["git", "status", "--short"],
            cwd=str(REPO_ROOT), capture_output=True, text=True, check=True, timeout=5,
        ).stdout.splitlines()
        return {"branch": branch, "head": head, "dirty": bool(short), "changes": short}
    except subprocess.SubprocessError as e:
        raise BackendError(f"git: {e}") from e


def git_log(n: int = 5) -> list[dict[str, Any]]:
    try:
        res = subprocess.run(
            ["git", "log", f"-{n}", "--pretty=format:%h|%H|%an|%ad|%s", "--date=iso-strict"],
            cwd=str(REPO_ROOT), capture_output=True, text=True, check=True, timeout=10,
        )
    except subprocess.SubprocessError as e:
        raise BackendError(f"git log: {e}") from e
    out: list[dict[str, Any]] = []
    for line in res.stdout.splitlines():
        parts = line.split("|", 4)
        if len(parts) == 5:
            out.append({"short": parts[0], "sha": parts[1], "author": parts[2],
                        "date": parts[3], "subject": parts[4]})
    return out


# ---------- Handovers ----------

def list_handovers() -> list[dict[str, Any]]:
    res = _script(MEMORY, "list", timeout=10)
    out: list[dict[str, Any]] = []
    for line in res.stdout.splitlines():
        raw = line.rstrip()
        if not raw.strip():
            continue
        # Format: "  * handover_005.md          2026-05-27 Title…"
        # First two chars are leading spaces; char 2 is marker (* or space).
        marker = raw[2:3] if len(raw) > 2 else " "
        rest = raw[4:] if len(raw) > 4 else raw.strip()
        parts = rest.split(None, 2)
        if not parts:
            continue
        item: dict[str, Any] = {
            "filename": parts[0],
            "date": parts[1] if len(parts) >= 2 else "",
            "title": parts[2] if len(parts) >= 3 else "",
            "status": "current" if marker == "*" else None,
        }
        out.append(item)
    return out


def new_handover(title: str = "") -> dict[str, Any]:
    args = ["create"]
    if title:
        args.extend(["--title", title])
    res = _script(MEMORY, *args, timeout=30)
    created = res.stdout.strip().splitlines()[0] if res.stdout.strip() else ""
    # Find prev (now superseded) by looking at the second entry in list output
    prev: str | None = None
    try:
        items = list_handovers()
        # items[0] is the new one (current); items[1] is the prior — now superseded
        if len(items) >= 2:
            prev = items[1]["filename"]
    except BackendError:
        prev = None
    return {"created": created, "prev_updated": prev or False}


# ---------- Swarm ----------

def swarm_preview() -> dict[str, Any]:
    res = _script(BUILD_WAVE, timeout=10)
    return json.loads(res.stdout or "{}")


# ---------- Helpers ----------

def next_task_id() -> str:
    """Generate the next available T### id by scanning existing tasks."""
    plan = get_plan()
    used: set[int] = set()
    for t in plan.get("tasks", []) or []:
        tid = t.get("id", "")
        if tid.startswith("T") and tid[1:].isdigit():
            used.add(int(tid[1:]))
    n = 1
    while n in used:
        n += 1
    return f"T{n:03d}"
