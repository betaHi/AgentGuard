"""CLI surface must be narrow for publishability."""

from __future__ import annotations

import io
import sys
from contextlib import redirect_stdout

import pytest

from agentguard.cli import main as cli


def _help_text() -> str:
    buf = io.StringIO()
    orig = sys.argv
    sys.argv = ["agentguard", "--help"]
    try:
        with redirect_stdout(buf):
            with pytest.raises(SystemExit):
                cli.main()
    finally:
        sys.argv = orig
    return buf.getvalue()


def test_core_commands_listed_in_help():
    text = _help_text()
    for cmd in (
        "list-claude-sessions",
        "diagnose-claude-session",
        "diagnose",
        "report",
        "doctor",
        "version",
    ):
        assert cmd in text, f"{cmd} should be visible in --help"


def test_legacy_commands_hidden_from_help():
    import re
    text = _help_text()
    for cmd in (
        "learn", "suggest", "trends", "prd", "auto-apply",
        "benchmark", "generate", "guard", "search", "aggregate",
        "merge", "merge-dir",
    ):
        # Word-boundary match: avoid false-positive on e.g. "agentguard" vs "guard".
        assert not re.search(rf"(?<![\w-]){re.escape(cmd)}(?![\w-])\s+[A-Z]", text), (
            f"{cmd} still leaking into --help"
        )


def test_legacy_commands_still_executable():
    """Hidden != removed. They must still run (backwards compat)."""
    # ``version`` is always wired up; for a legacy command, just prove the
    # parser still accepts it without an error message.
    import argparse
    parser = argparse.ArgumentParser(prog="agentguard")
    sub = parser.add_subparsers(dest="command")
    cli._register_subcommands(sub)
    cli._register_analysis_commands(sub)
    cli._register_comparison_commands(sub)
    cli._register_ops_commands(sub)
    cli._hide_non_core_commands(sub)

    args = parser.parse_args(["learn", "/tmp/does-not-exist.json"])
    assert args.command == "learn"
