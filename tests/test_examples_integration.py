"""Integration test: run all examples, verify exit code 0 + output sanity.

This is the definitive integration test for examples. Checks:
1. Exit code 0
2. Produces stdout output (not silent)
3. No unhandled exceptions in stderr
4. Output length is reasonable (not empty, not suspiciously short)
"""

import subprocess
import sys
import os
import glob
import pytest

EXAMPLES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "examples")
ALL_EXAMPLES = sorted(glob.glob(os.path.join(EXAMPLES_DIR, "*.py")))

# Minimal examples that may have very short output
MINIMAL_OUTPUT = {"minimal.py", "data_pipeline.py", "async_demo.py",
                  "content_pipeline.py", "security_pipeline.py"}


def _run(path, timeout=30):
    return subprocess.run(
        [sys.executable, path],
        capture_output=True, text=True, timeout=timeout,
        cwd=os.path.dirname(EXAMPLES_DIR),
    )


class TestExamplesIntegration:
    @pytest.mark.parametrize("path", ALL_EXAMPLES,
                             ids=[os.path.basename(p) for p in ALL_EXAMPLES])
    def test_exit_code_zero(self, path):
        r = _run(path)
        assert r.returncode == 0, (
            f"{os.path.basename(path)} failed (rc={r.returncode}):\n"
            f"{r.stderr[-300:]}"
        )

    @pytest.mark.parametrize("path", ALL_EXAMPLES,
                             ids=[os.path.basename(p) for p in ALL_EXAMPLES])
    def test_produces_output(self, path):
        """Example should produce some stdout (not completely silent)."""
        r = _run(path)
        name = os.path.basename(path)
        if name not in MINIMAL_OUTPUT:
            assert len(r.stdout) > 10, f"{name} produced no output"

    @pytest.mark.parametrize("path", ALL_EXAMPLES,
                             ids=[os.path.basename(p) for p in ALL_EXAMPLES])
    def test_no_unhandled_exception(self, path):
        r = _run(path)
        assert "Traceback (most recent call last)" not in r.stderr, (
            f"{os.path.basename(path)} has unhandled exception:\n{r.stderr[-500:]}"
        )

    @pytest.mark.parametrize("path", ALL_EXAMPLES,
                             ids=[os.path.basename(p) for p in ALL_EXAMPLES])
    def test_no_import_error(self, path):
        r = _run(path)
        combined = r.stdout + r.stderr
        assert "ImportError" not in combined, f"{os.path.basename(path)} has ImportError"
        assert "ModuleNotFoundError" not in combined, f"{os.path.basename(path)} missing module"
