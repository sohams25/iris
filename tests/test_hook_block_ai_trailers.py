"""block-ai-commit-trailers.sh hook — block / allow scenarios."""
from __future__ import annotations
import base64
import json
import os
import subprocess
from pathlib import Path



HOOK = Path(__file__).resolve().parent.parent / ".claude" / "hooks" / "block-ai-commit-trailers.sh"


def b64(s: str) -> str:
    return base64.b64decode(s).decode("utf-8")


def run_hook(payload: dict, timeout: int = 5) -> int:
    proc = subprocess.run(
        ["bash", str(HOOK)],
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    return proc.returncode


def test_clean_commit_allowed():
    assert run_hook({
        "tool_name": "Bash",
        "tool_input": {"command": 'git commit -m "fix: bump retry from 3 to 5"'},
    }) == 0


def test_robot_emoji_footer_blocked():
    msg = "feat: x\n\n" + b64("8J+klyBHZW5lcmF0ZWQgd2l0aCBbQ2xhdWRlIENvZGVdKGh0dHBzOi8vY2xhdWRlLmNvbS9jbGF1ZGUtY29kZSk=")
    assert run_hook({
        "tool_name": "Bash",
        "tool_input": {"command": "git commit -m " + json.dumps(msg, ensure_ascii=False)},
    }) == 2


def test_coauthor_footer_blocked():
    msg = "fix: x\n\n" + b64("Q28tQXV0aG9yZWQtQnk6IENsYXVkZSA8bm9yZXBseUBhbnRocm9waWMuY29tPg==")
    assert run_hook({
        "tool_name": "Bash",
        "tool_input": {"command": "git commit -m " + json.dumps(msg, ensure_ascii=False)},
    }) == 2


def test_non_git_passes_through():
    assert run_hook({"tool_name": "Bash", "tool_input": {"command": "ls -la"}}) == 0


def test_git_commit_no_message_passes_through():
    """Editor-path commit: hook cannot see the message, fails open."""
    assert run_hook({"tool_name": "Bash", "tool_input": {"command": "git commit"}}) == 0


def test_empty_payload_passes_through():
    assert run_hook({}) == 0


def test_git_tag_with_emoji_footer_blocked():
    msg = b64("8J+klyBHZW5lcmF0ZWQgd2l0aCBDbGF1ZGUgQ29kZQ==")
    assert run_hook({
        "tool_name": "Bash",
        "tool_input": {"command": "git tag v1.0 -m " + json.dumps(msg, ensure_ascii=False)},
    }) == 2


def test_prose_adjectives_not_flagged():
    """'comprehensive' is a stop-slop concern, not a commit-style concern."""
    assert run_hook({
        "tool_name": "Bash",
        "tool_input": {"command": 'git commit -m "feat: comprehensive rewrite of foo"'},
    }) == 0


def test_forbidden_string_in_filename_does_not_block():
    """Path arguments to non-commit commands are not message bodies."""
    assert run_hook({
        "tool_name": "Bash",
        "tool_input": {"command": "ls /tmp/Co-Authored-By-Claude-test.txt"},
    }) == 0


def test_message_file_clean_allowed(tmp_path):
    msg_file = tmp_path / "msg.txt"
    msg_file.write_text("fix: bump x")
    assert run_hook({
        "tool_name": "Bash",
        "tool_input": {"command": f"git commit -F {msg_file}"},
    }) == 0


def test_message_file_with_ai_footer_blocked(tmp_path):
    msg_file = tmp_path / "msg.txt"
    msg_file.write_text("fix: x\n\n" + b64("Q28tQXV0aG9yZWQtQnk6IENsYXVkZSA8bm9yZXBseUBhbnRocm9waWMuY29tPg=="))
    assert run_hook({
        "tool_name": "Bash",
        "tool_input": {"command": f"git commit -F {msg_file}"},
    }) == 2


def test_message_file_missing_passes_through():
    assert run_hook({
        "tool_name": "Bash",
        "tool_input": {"command": "git commit -F /tmp/does-not-exist-9999.txt"},
    }) == 0


def test_directory_as_message_path_passes_through(tmp_path):
    """A directory passed as -F is not a regular file; skip and fail open."""
    assert run_hook({
        "tool_name": "Bash",
        "tool_input": {"command": f"git commit -F {tmp_path}"},
    }) == 0


def test_fifo_as_message_path_does_not_hang(tmp_path):
    """A FIFO with no writer would block open() forever. Verify the hook
    refuses to read non-regular files."""
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)
    # the timeout in run_hook catches the hang case
    assert run_hook({
        "tool_name": "Bash",
        "tool_input": {"command": f"git commit -F {fifo}"},
    }, timeout=5) == 0


def test_stdin_dash_message_passes_through():
    """`-F -` reads from stdin; we cannot re-read it, so fail open."""
    assert run_hook({
        "tool_name": "Bash",
        "tool_input": {"command": "git commit -F -"},
    }) == 0
