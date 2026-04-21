"""Tests for Claude Code standalone and plugin scaffolds."""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
from pathlib import Path


def test_plugin_manifest_and_skills_exist() -> None:
    root = Path(__file__).resolve().parents[1]
    plugin_root = root / "plugins" / "agentguard-claude-code"
    manifest = plugin_root / ".claude-plugin" / "plugin.json"
    diagnose_session = plugin_root / "skills" / "diagnose-session" / "SKILL.md"
    diagnose_trace = plugin_root / "skills" / "diagnose-trace" / "SKILL.md"
    list_sessions = plugin_root / "skills" / "list-sessions" / "SKILL.md"

    assert manifest.exists()
    assert diagnose_session.exists()
    assert diagnose_trace.exists()
    assert list_sessions.exists()

    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["name"] == "agentguard"
    assert "diagnostics" in data["description"].lower()
    session_text = diagnose_session.read_text(encoding="utf-8")
    trace_text = diagnose_trace.read_text(encoding="utf-8")
    list_text = list_sessions.read_text(encoding="utf-8")
    assert "name: diagnose-session" in session_text
    assert "diagnose-claude-session" in session_text
    assert "list-claude-sessions" in session_text
    # The skill must make session id optional and use a picker flow.
    assert "optional" in session_text.lower()
    assert "Do NOT auto-pick" in session_text
    assert "name: diagnose-trace" in trace_text
    # list-sessions skill must call the cross-project grouped listing.
    assert "name: list-sessions" in list_text
    assert "--all" in list_text
    assert "--group-by-project" in list_text
    # The *default* invocation must be bounded so the Claude Code bash
    # tool doesn't choke on hundreds of lines of output; only the
    # explicit "list all" path should use --all.
    assert "--limit 20 --group-by-project" in list_text

    # All plugin skills must dispatch through the bundled launcher, not a
    # bare `agentguard` command, so they work even when the user hasn't
    # activated any Python environment.
    for skill_text in (session_text, trace_text, list_text):
        assert "${CLAUDE_PLUGIN_ROOT}/bin/agentguard" in skill_text


def test_plugin_bundles_agentguard_launcher() -> None:
    root = Path(__file__).resolve().parents[1]
    launcher = root / "plugins" / "agentguard-claude-code" / "bin" / "agentguard"

    assert launcher.exists(), "plugin must bundle bin/agentguard launcher"
    mode = launcher.stat().st_mode
    assert mode & stat.S_IXUSR, "launcher must be executable"

    text = launcher.read_text(encoding="utf-8")
    # Sanity: launcher should mention its primary resolution strategies.
    assert "AGENTGUARD_BIN" in text
    assert "command -v agentguard" in text
    assert "python3 -m agentguard" in text or "-m agentguard" in text


def test_launcher_honors_agentguard_bin_override(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    launcher = root / "plugins" / "agentguard-claude-code" / "bin" / "agentguard"

    stub = tmp_path / "fake-ag"
    stub.write_text(
        "#!/usr/bin/env bash\n"
        'echo "STUB_CALLED $*"\n',
        encoding="utf-8",
    )
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)

    # Stripped environment so no real agentguard is on PATH; the override
    # must be the only thing that matters.
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(tmp_path),
        "AGENTGUARD_BIN": str(stub),
    }
    bash = shutil.which("bash") or "/bin/bash"
    result = subprocess.run(
        [bash, str(launcher), "version"],
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert "STUB_CALLED version" in result.stdout


def test_launcher_exits_127_when_nothing_resolves(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    launcher = root / "plugins" / "agentguard-claude-code" / "bin" / "agentguard"

    env = {
        "PATH": "/usr/bin:/bin",  # no agentguard, no python with agentguard installed at sys level
        "HOME": str(tmp_path),  # so ~/AgentGuard/.venv/... does not resolve
    }
    # Ensure no stray system-wide `agentguard` on the minimal PATH masks the
    # "nothing found" path. If there happens to be one, skip this assertion.
    resolved = shutil.which("agentguard", path=env["PATH"])
    if resolved:
        return
    # And skip if a system python actually imports agentguard (unlikely).
    probe = subprocess.run(
        ["/usr/bin/env", "python3", "-c", "import agentguard"],
        capture_output=True,
        env=env,
        timeout=10,
    )
    if probe.returncode == 0:
        return

    bash = shutil.which("bash") or "/bin/bash"
    result = subprocess.run(
        [bash, str(launcher), "version"],
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )
    assert result.returncode == 127
    assert "agentguard not found" in result.stderr


def test_standalone_skill_exists() -> None:
    root = Path(__file__).resolve().parents[1]
    skill = root / ".claude" / "skills" / "agentguard-diagnose-session" / "SKILL.md"

    assert skill.exists()
    text = skill.read_text(encoding="utf-8")
    assert "name: agentguard-diagnose-session" in text
    assert "diagnose-claude-session" in text


def test_plugin_hooks_reference_executable_script() -> None:
    root = Path(__file__).resolve().parents[1]
    plugin_root = root / "plugins" / "agentguard-claude-code"
    hooks_file = plugin_root / "hooks" / "hooks.json"
    script = plugin_root / "scripts" / "post-session-diagnose.sh"

    assert hooks_file.exists()
    assert script.exists()

    hooks = json.loads(hooks_file.read_text(encoding="utf-8"))
    entries = hooks["hooks"]["SessionEnd"]
    commands = [h["command"] for entry in entries for h in entry["hooks"]]
    assert any("post-session-diagnose.sh" in c for c in commands)
    assert all(c.startswith("${CLAUDE_PLUGIN_ROOT}/") for c in commands)

    mode = script.stat().st_mode
    assert mode & stat.S_IXUSR, "hook script must be executable"


def test_post_session_diagnose_script_is_noop_without_session_id(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    script = root / "plugins" / "agentguard-claude-code" / "scripts" / "post-session-diagnose.sh"

    result = subprocess.run(
        ["bash", str(script)],
        input="{}",
        capture_output=True,
        text=True,
        cwd=tmp_path,
        timeout=10,
    )
    assert result.returncode == 0
    assert not (tmp_path / ".agentguard").exists()


def test_post_session_diagnose_script_dispatches_with_session_id(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    script = root / "plugins" / "agentguard-claude-code" / "scripts" / "post-session-diagnose.sh"

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    stub = fake_bin / "agentguard"
    stub.write_text(
        "#!/usr/bin/env bash\n"
        "mkdir -p .agentguard/marker\n"
        "printf '%s\\n' \"$@\" > .agentguard/marker/args.txt\n",
        encoding="utf-8",
    )
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"

    result = subprocess.run(
        ["bash", str(script)],
        input='{"session_id": "sess-123"}',
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env=env,
        timeout=10,
    )
    assert result.returncode == 0

    # Hook backgrounds the work; wait briefly for the stub to run.
    import time

    deadline = time.time() + 5
    args_file = tmp_path / ".agentguard" / "marker" / "args.txt"
    while time.time() < deadline and not args_file.exists():
        time.sleep(0.05)

    assert args_file.exists(), "stub agentguard was not invoked"
    args_text = args_file.read_text(encoding="utf-8")
    assert "diagnose-claude-session" in args_text
    assert "sess-123" in args_text
    assert "--output" in args_text
    assert "--report-output" in args_text


def test_post_session_diagnose_script_exits_silently_without_agentguard(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    script = root / "plugins" / "agentguard-claude-code" / "scripts" / "post-session-diagnose.sh"

    bash = shutil.which("bash") or "/bin/bash"

    # Point CLAUDE_PLUGIN_ROOT at a directory that has NO bin/agentguard
    # launcher and restrict PATH so no fallback `agentguard` is found.
    fake_plugin_root = tmp_path / "fake-plugin-root"
    fake_plugin_root.mkdir()

    env = os.environ.copy()
    env["PATH"] = "/usr/bin:/bin"
    env["CLAUDE_PLUGIN_ROOT"] = str(fake_plugin_root)
    assert shutil.which("agentguard", path=env["PATH"]) is None

    result = subprocess.run(
        [bash, str(script)],
        input='{"session_id": "sess-xyz"}',
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env=env,
        timeout=10,
    )
    assert result.returncode == 0
    assert not (tmp_path / ".agentguard").exists()