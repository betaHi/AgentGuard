"""Contract test: Claude SDK version guard rail.

This is the *shape* contract — the real SDK integration test lives with
the rest of the import fidelity tests. Here we pin down the version guard
so a future SDK upgrade cannot silently break diagnostics.
"""

from __future__ import annotations

import sys
import types

import pytest

from agentguard.runtime.claude.session_import import (
    ClaudeSessionImportError,
    _assert_sdk_version_supported,
    _parse_sdk_version,
    _SDK_MAX_EXCLUSIVE,
    _SDK_MIN_VERSION,
    _load_sdk_module,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0.5.0", (0, 5, 0)),
        ("0.7.3", (0, 7, 3)),
        ("0.6", (0, 6, 0)),
        ("1.0.0+build.5", (1, 0, 0)),
        ("0.5.0-rc1", (0, 5, 0)),
        ("not-a-version", None),
        ("", None),
    ],
)
def test_parse_sdk_version(raw, expected):
    assert _parse_sdk_version(raw) == expected


def _fake_sdk(version: str | None) -> object:
    fake = types.SimpleNamespace()
    if version is not None:
        fake.__version__ = version
    return fake


def test_supported_version_passes():
    _assert_sdk_version_supported(_fake_sdk("0.5.0"))
    _assert_sdk_version_supported(_fake_sdk("0.7.9"))


def test_too_old_version_is_rejected_with_install_hint():
    with pytest.raises(ClaudeSessionImportError) as excinfo:
        _assert_sdk_version_supported(_fake_sdk("0.4.0"))
    msg = str(excinfo.value)
    assert "0.4.0" in msg
    assert "pip install" in msg
    assert "claude-agent-sdk" in msg


def test_too_new_version_is_rejected():
    max_v = ".".join(str(p) for p in _SDK_MAX_EXCLUSIVE)
    with pytest.raises(ClaudeSessionImportError) as excinfo:
        _assert_sdk_version_supported(_fake_sdk(max_v))
    assert max_v in str(excinfo.value)


def test_missing_version_attr_is_allowed():
    # Development builds sometimes strip __version__; we must not fail.
    _assert_sdk_version_supported(_fake_sdk(None))


def test_unparseable_version_is_allowed():
    # Future tagging schemes shouldn't block imports outright.
    _assert_sdk_version_supported(_fake_sdk("something-weird"))


def test_missing_sdk_raises_actionable_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", None)

    # Force ImportError by making the module lookup fail:
    real_import = __import__

    def broken_import(name, *args, **kwargs):
        if name == "claude_agent_sdk":
            raise ImportError("no module")
        return real_import(name, *args, **kwargs)

    import builtins
    monkeypatch.setattr(builtins, "__import__", broken_import)

    with pytest.raises(ClaudeSessionImportError) as excinfo:
        _load_sdk_module()
    msg = str(excinfo.value)
    assert "pip install" in msg
    assert "agentguard[claude]" in msg


def test_pyproject_extra_matches_code_version_range():
    """Guard-rail so pyproject and source don't drift."""
    import pathlib
    pyproject = pathlib.Path(__file__).parent.parent / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    min_s = ".".join(str(p) for p in _SDK_MIN_VERSION)
    max_s = ".".join(str(p) for p in _SDK_MAX_EXCLUSIVE)
    expected = f"claude-agent-sdk>={min_s},<{max_s}"
    assert expected in text, (
        f"pyproject claude extra must declare {expected!r} to match session_import.py"
    )
