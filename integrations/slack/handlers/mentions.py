"""Handle @bot mentions.

Parses the mention text into an Intent and dispatches to the appropriate
backend action. Always replies in-thread on the original message so the
channel doesn't get spammed at root level.
"""
from __future__ import annotations

import logging

from integrations.slack import client
from integrations.slack.parser import Intent, parse

log = logging.getLogger("slackbot.mentions")


HELP_TEXT = """*Available commands* (mention me or use slash commands):

*Loop control*
• `@me run loop` — start the autonomous loop
• `@me run loop max=20 minutes=60 dry` — with overrides
• `@me stop loop` — kill the running loop
• `@me status` — current state of everything

*Backlog*
• `@me tasks` — list open tasks
• `@me add task: <description>` — create a task
• `@me add task: <description> files: src/x.ts, src/y.ts priority: 3`
• `@me pass T007` — mark task as passed
• `@me block T007: <reason>` — mark task blocked

*Continuity & swarm*
• `@me handover new: <title>` — generate next handover
• `@me handover current` — link to current handover
• `@me swarm` — wave plan preview

*Slash commands* — same effect:
• `/loop start|stop|status`
• `/tasks list|add <desc>`
• `/handover new <title>|current`
"""


def _format_status() -> str:
    plan = client.get_plan()
    loop = client.loop_status()
    git = client.git_status()
    handovers = client.list_handovers()
    tasks = plan.get("tasks", [])
    opens = [t for t in tasks if not t.get("passes") and not t.get("blocked")]
    blocked = [t for t in tasks if t.get("blocked")]
    passed = [t for t in tasks if t.get("passes")]
    current_h = next((h for h in handovers if h.get("status") == "current"), None)

    lines = ["*Workspace status*"]
    lines.append(
        f"• Loop: {'🟢 running' if loop.get('running') else '⚪ idle'}"
        + (f" (pid {loop['pid']})" if loop.get("running") else "")
    )
    lines.append(
        f"• Backlog: *{len(opens)}* open · {len(blocked)} blocked · {len(passed)} done"
    )
    lines.append(f"• Branch: `{git.get('branch')}` @ `{git.get('head')}`"
                 + (" (dirty)" if git.get('dirty') else " (clean)"))
    if current_h:
        lines.append(f"• Current handover: `{current_h['filename']}` — {current_h.get('title') or '(untitled)'}")
    if opens:
        lines.append("")
        lines.append("*Next up:*")
        for t in sorted(opens, key=lambda x: (x.get("priority", 999), x.get("id", "")))[:5]:
            lines.append(f"  • `{t['id']}` P{t.get('priority')} — {t.get('title')}")
    return "\n".join(lines)


def _format_tasks() -> str:
    plan = client.get_plan()
    tasks = plan.get("tasks", [])
    opens = sorted(
        [t for t in tasks if not t.get("passes") and not t.get("blocked")],
        key=lambda x: (x.get("priority", 999), x.get("id", "")),
    )
    if not opens:
        return "_No open tasks._ Backlog is empty or everything is done/blocked."
    lines = ["*Open tasks*"]
    for t in opens:
        files_part = ""
        if t.get("files"):
            files_part = f"  _files:_ `{', '.join(t['files'])}`"
        lines.append(f"• `{t['id']}` P{t.get('priority')} — {t.get('title')}{files_part}")
    blocked = [t for t in tasks if t.get("blocked")]
    if blocked:
        lines.append("")
        lines.append("*Blocked:*")
        for t in blocked:
            lines.append(f"• `{t['id']}` — {t.get('title')} _({(t.get('notes') or '').splitlines()[0] if t.get('notes') else 'no reason'})_")
    return "\n".join(lines)


def _format_swarm() -> str:
    plan = client.swarm_preview()
    waves = plan.get("waves", [])
    stats = plan.get("stats", {})
    if not waves:
        return "_No open tasks to plan._"
    lines = [
        f"*Wave plan* — {stats.get('total_tasks')} tasks · {stats.get('wave_count')} waves"
    ]
    for w in waves:
        ids = ", ".join(f"`{t['id']}`" for t in w["tasks"])
        kind = "parallel" if len(w["tasks"]) > 1 else "serial"
        lines.append(f"• *Wave {w['id']}* ({kind}): {ids}")
    lines.append("\n_Actual execution still happens inside Claude Code: type `/run` in a session there — it auto-routes to parallel when the work allows._")
    return "\n".join(lines)


def _handle_add_task(intent: Intent) -> str:
    title = intent.params.get("title", "")
    files = intent.params.get("files", [])
    priority = intent.params.get("priority")
    tid = client.next_task_id()
    res = client.add_task(tid, title=title, files=files or None, priority=priority)
    t = res.get("task", {})
    out = f"✅ Created `{t.get('id')}` (priority {t.get('priority')}): _{t.get('title')}_"
    if t.get("files"):
        out += f"\n   files: `{', '.join(t['files'])}`"
    return out


def _handle_run_loop(intent: Intent) -> str:
    p = intent.params
    res = client.loop_start(
        max_iterations=p.get("max_iterations", 50),
        max_minutes=p.get("max_minutes", 480),
        dry_run=p.get("dry_run", False),
    )
    if res.get("started"):
        s = res.get("status", {})
        dry = " (dry-run)" if p.get("dry_run") else ""
        return (
            f"🚀 *Loop started*{dry}\n"
            f"• max iterations: {p.get('max_iterations', 50)}\n"
            f"• max minutes: {p.get('max_minutes', 480)}\n"
            f"• pid: `{s.get('pid')}`\n"
            f"\nI'll post updates here as tasks complete or block."
        )
    return f"⚠️ Did not start: {res.get('reason', 'unknown')}"


def _handle_stop_loop() -> str:
    res = client.loop_stop()
    if res.get("stopped"):
        return f"🛑 Loop stopped (exit code: `{res.get('exit_code')}`)"
    return f"_Nothing to stop._ {res.get('detail', 'not running')}"


def _handle_pass(intent: Intent) -> str:
    tid = intent.params["task_id"]
    client.patch_task(tid, passes=True, blocked=False)
    return f"✅ `{tid}` marked as passed."


def _handle_block(intent: Intent) -> str:
    tid = intent.params["task_id"]
    reason = intent.params.get("reason", "")
    patch = {"blocked": True, "passes": False}
    if reason:
        # Append, don't overwrite
        plan = client.get_plan()
        task = next((t for t in plan["tasks"] if t.get("id") == tid), None)
        existing = (task or {}).get("notes") or ""
        sep = "\n" if existing else ""
        patch["notes"] = f"{existing}{sep}[via slack] {reason}"
    client.patch_task(tid, **patch)
    return f"⛔ `{tid}` marked as blocked. _{reason or 'no reason given'}_"


def _handle_handover_new(intent: Intent) -> str:
    title = intent.params.get("title", "")
    res = client.new_handover(title)
    return (
        f"📝 Created handover `{res.get('created')}`"
        + (f"\n   previous (`{res.get('prev_updated')}`) updated → superseded" if res.get("prev_updated") else "")
        + f"\n   _path: handovers/{res.get('created')}_"
    )


def _handle_handover_current() -> str:
    handovers = client.list_handovers()
    current = next((h for h in handovers if h.get("status") == "current"), None)
    if not current:
        return "_No current handover._"
    return (
        f"📖 Current handover: `{current['filename']}`\n"
        f"_{current.get('title') or '(untitled)'}_ ({current.get('date')})\n"
        f"_path: handovers/{current['filename']}_"
    )


def dispatch(text: str) -> str:
    """Parse text into an Intent and produce a Slack-formatted reply."""
    try:
        intent = parse(text)
        log.info("intent: %s params=%s", intent.kind, intent.params)
        if intent.kind == "help":
            return HELP_TEXT
        if intent.kind == "status":
            return _format_status()
        if intent.kind == "list_tasks":
            return _format_tasks()
        if intent.kind == "swarm":
            return _format_swarm()
        if intent.kind == "add_task":
            return _handle_add_task(intent)
        if intent.kind == "run_loop":
            return _handle_run_loop(intent)
        if intent.kind == "stop_loop":
            return _handle_stop_loop()
        if intent.kind == "pass_task":
            return _handle_pass(intent)
        if intent.kind == "block_task":
            return _handle_block(intent)
        if intent.kind == "handover_new":
            return _handle_handover_new(intent)
        if intent.kind == "handover_current":
            return _handle_handover_current()
        # Unknown
        return (
            "🤔 I didn't understand that. Try `@me help` for the full list, or:\n"
            "• `@me status`\n• `@me tasks`\n• `@me add task: <description>`\n• `@me run loop`"
        )
    except client.BackendError as e:
        return f"❌ Backend error: `{e}`\n_Check `python3 scripts/doctor.py` and `scripts/memory.py current`._"
    except Exception as e:
        log.exception("dispatch failed")
        return f"❌ Internal error: `{type(e).__name__}: {e}`"
