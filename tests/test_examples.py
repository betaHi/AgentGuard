"""Consolidated integration test for all examples.

Runs each example as a subprocess and checks:
1. Exit code 0 (no crashes)
2. Produces stdout output (not silent)
3. No unhandled exceptions (no Traceback in stderr)
4. No ImportError/ModuleNotFoundError
5. No misleading zero-duration traces
6. No '0 spans' output

Replaces: test_examples_smoke.py, test_examples_no_misleading.py,
           test_examples_integration.py
"""

import glob
import os
import subprocess
import sys

import pytest

EXAMPLES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "examples")
ALL_EXAMPLES = sorted(glob.glob(os.path.join(EXAMPLES_DIR, "*.py")))

# Examples with intentionally minimal output
MINIMAL_OUTPUT = {"minimal.py", "data_pipeline.py", "async_demo.py",
                  "content_pipeline.py", "security_pipeline.py"}


@pytest.fixture(scope="module")
def example_outputs():
    """Run all examples once and cache results.

    Returns dict mapping basename → CompletedProcess.
    Running once instead of 3–4× saves ~2 minutes of CI time.
    """
    results = {}
    for path in ALL_EXAMPLES:
        name = os.path.basename(path)
        results[name] = subprocess.run(
            [sys.executable, path],
            capture_output=True, text=True, timeout=30,
            cwd=os.path.dirname(EXAMPLES_DIR),
        )
    return results


def _ids():
    return [os.path.basename(p) for p in ALL_EXAMPLES]


@pytest.fixture(params=ALL_EXAMPLES, ids=_ids())
def example_result(request, example_outputs):
    """Yield (name, CompletedProcess) for each example."""
    name = os.path.basename(request.param)
    return name, example_outputs[name]


class TestExamples:
    """All example validation in one class, one subprocess run per example."""

    def test_exit_code_zero(self, example_result):
        """Example must exit cleanly."""
        name, r = example_result
        assert r.returncode == 0, (
            f"{name} crashed (rc={r.returncode}):\n{r.stderr[-300:]}"
        )

    def test_produces_output(self, example_result):
        """Non-trivial examples must produce stdout."""
        name, r = example_result
        if name not in MINIMAL_OUTPUT:
            assert len(r.stdout) > 10, f"{name} produced no output"

    def test_no_traceback(self, example_result):
        """No unhandled Python exceptions."""
        name, r = example_result
        assert "Traceback (most recent call last)" not in r.stderr, (
            f"{name} has exception:\n{r.stderr[-500:]}"
        )

    def test_no_import_error(self, example_result):
        """All imports must resolve."""
        name, r = example_result
        combined = r.stdout + r.stderr
        assert "ImportError" not in combined, f"{name} has ImportError"
        assert "ModuleNotFoundError" not in combined, f"{name} missing module"

    def test_no_zero_duration_trace(self, example_result):
        """Trace duration should not be 0ms (broken timing)."""
        name, r = example_result
        if name not in {"minimal.py"}:
            assert "Duration: 0ms" not in r.stdout, (
                f"{name} shows Duration: 0ms"
            )

    def test_no_zero_spans(self, example_result):
        """Should not report '0 spans'."""
        name, r = example_result
        assert "0 spans" not in r.stdout, f"{name} shows 0 spans"


def test_example_count():
    """Guard: new examples must be included in this test."""
    assert len(ALL_EXAMPLES) >= 20, (
        f"Expected ≥20 examples, found {len(ALL_EXAMPLES)}. "
        "If you added examples, they're auto-included."
    )
