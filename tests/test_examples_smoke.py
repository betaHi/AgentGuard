"""Smoke tests for all 18 examples — verify they run without crashing.

Audit: every example in examples/ must be tested here.
If an example is added, a test must be added too.
"""

import glob
import os
import subprocess
import sys

import pytest

EXAMPLES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "examples")
ALL_EXAMPLES = sorted(
    os.path.basename(f)
    for f in glob.glob(os.path.join(EXAMPLES_DIR, "*.py"))
)


def _run_example(name, timeout=30):
    """Run an example script and return CompletedProcess."""
    path = os.path.join(EXAMPLES_DIR, name)
    if not os.path.exists(path):
        pytest.skip(f"{name} not found")
    return subprocess.run(
        [sys.executable, path],
        capture_output=True, text=True, timeout=timeout,
        cwd=os.path.dirname(EXAMPLES_DIR),
    )


class TestExamplesSmoke:
    """Each example should run without errors."""

    @pytest.mark.parametrize("example", ALL_EXAMPLES)
    def test_example_runs(self, example):
        result = _run_example(example)
        assert result.returncode == 0, (
            f"{example} failed (rc={result.returncode}):\n{result.stderr[-500:]}"
        )

    def test_all_18_examples_covered(self):
        """Ensure we have exactly 18 examples."""
        assert len(ALL_EXAMPLES) >= 18, (
            f"Expected ≥18 examples, found {len(ALL_EXAMPLES)}: {ALL_EXAMPLES}"
        )
