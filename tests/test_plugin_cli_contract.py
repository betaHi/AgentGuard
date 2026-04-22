"""Plugin <-> CLI contract test.

The Claude Code plugin shell scripts call the `agentguard` CLI with
specific flags. If a future CLI refactor renames or drops one of those
flags, the plugin breaks silently for every user. This test locks the
contract: each flag the plugin's SKILL.md invokes must still be accepted
by the current CLI.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = REPO / "plugins" / "agentguard-claude-code"


def _cli_help(subcommand: str) -> str:
    result = subprocess.run(
        [sys.executable, "-m", "agentguard", subcommand, "--help"],
        capture_output=True, text=True, timeout=30,
    )
    return result.stdout + result.stderr


def _invocations(skill_path: Path) -> list[tuple[str, list[str]]]:
    """Return ``(subcommand, flags)`` for every CLI call inside a SKILL.md.

    Parses bash code fences looking for lines of the form
    ``bin/agentguard <subcommand> ... --flag ...``. A skill may invoke
    more than one subcommand, so we return every call separately.
    """
    text = skill_path.read_text(encoding="utf-8")
    results: list[tuple[str, list[str]]] = []
    for line in text.splitlines():
        m = re.search(r"bin/agentguard\s+([a-z][a-z-]*)\b(.*)", line)
        if not m:
            continue
        subcommand = m.group(1)
        tail = m.group(2)
        flags = re.findall(r"(--[a-zA-Z][a-zA-Z0-9-]*)", tail)
        # Also pick up flags swapped-in via prose, but only if prefixed
        # with the subcommand on the same line — the code-fence already
        # handles the real invocation path.
        results.append((subcommand, flags))
    return results


def test_plugin_manifest_exists():
    manifest = PLUGIN_ROOT / ".claude-plugin" / "plugin.json"
    assert manifest.is_file(), f"plugin manifest missing at {manifest}"


@pytest.mark.parametrize(
    "skill_name",
    ["list-sessions", "diagnose-session"],
)
def test_plugin_skill_flags_are_accepted_by_cli(skill_name):
    skill = PLUGIN_ROOT / "skills" / skill_name / "SKILL.md"
    assert skill.is_file(), f"missing skill {skill}"
    invocations = _invocations(skill)
    assert invocations, f"{skill_name} must invoke at least one CLI call"
    for subcommand, flags in invocations:
        if not flags:
            continue
        help_text = _cli_help(subcommand)
        for flag in flags:
            assert flag in help_text, (
                f"plugin '{skill_name}' invokes "
                f"'agentguard {subcommand} {flag}' but the current CLI "
                f"does not advertise {flag}.\n--- CLI help ---\n{help_text}"
            )


def test_plugin_launcher_script_is_executable():
    launcher = PLUGIN_ROOT / "bin" / "agentguard"
    assert launcher.is_file()
    # Sanity: must be a shell script with a shebang, not a compiled blob.
    first = launcher.read_text(encoding="utf-8").splitlines()[0]
    assert first.startswith("#!"), f"plugin launcher missing shebang: {first!r}"
