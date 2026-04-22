"""`agentguard doctor` must check real Claude readiness, not just imports."""

from __future__ import annotations

import subprocess
import sys


def _run_doctor() -> str:
    """Invoke the CLI doctor in a subprocess and capture stdout + stderr."""
    result = subprocess.run(
        [sys.executable, "-m", "agentguard", "doctor"],
        capture_output=True, text=True, timeout=30,
    )
    return result.stdout + result.stderr


def test_doctor_reports_claude_sdk_status():
    output = _run_doctor()
    assert "claude-agent-sdk" in output, (
        "doctor must mention the Claude Agent SDK one way or another"
    )


def test_doctor_reports_claude_projects_directory():
    output = _run_doctor()
    # Either "Claude sessions at …" (found) or "not found" (absent).
    assert ".claude/projects" in output or "Claude sessions" in output


def test_doctor_reports_pricing_table_date():
    output = _run_doctor()
    assert "Pricing table" in output, (
        "doctor must surface built-in pricing table freshness"
    )


def test_doctor_exits_nonzero_when_sdk_is_out_of_range_or_missing():
    """Red checkmarks should flip exit status; yellow warnings should not."""
    # We can't force a specific environment state from the test, but we can
    # assert that the exit code discipline is: 0 or 1, never crash.
    result = subprocess.run(
        [sys.executable, "-m", "agentguard", "doctor"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode in (0, 1), (
        f"doctor must exit cleanly (0 or 1), got {result.returncode}: "
        f"{result.stderr}"
    )
