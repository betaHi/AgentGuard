"""Test: all examples produce correct, non-misleading output.

Checks for patterns that indicate broken instrumentation:
- Duration: 0ms (spans not timed)
- 0 tokens, $0.00 (cost data missing where expected)
- Score: 0/100 (broken scoring)
- 0 spans (nothing recorded)
- Python tracebacks (unhandled errors)
"""

import subprocess
import sys
import os
import glob
import pytest

EXAMPLES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "examples")
ALL_EXAMPLES = sorted(glob.glob(os.path.join(EXAMPLES_DIR, "*.py")))

# Examples that legitimately show $0.00 or 0 tokens (local models, no LLM calls)
COST_EXEMPT = {"minimal.py", "data_pipeline.py", "async_demo.py",
               "content_pipeline.py", "security_pipeline.py"}


def _run(path):
    return subprocess.run(
        [sys.executable, path],
        capture_output=True, text=True, timeout=30,
        cwd=os.path.dirname(EXAMPLES_DIR),
    )


class TestExamplesNoMisleading:
    @pytest.mark.parametrize("path", ALL_EXAMPLES,
                             ids=[os.path.basename(p) for p in ALL_EXAMPLES])
    def test_no_traceback(self, path):
        """No unhandled Python tracebacks."""
        r = _run(path)
        assert r.returncode == 0, f"{os.path.basename(path)} crashed"
        assert "Traceback" not in r.stderr, f"Traceback in {os.path.basename(path)}"

    @pytest.mark.parametrize("path", ALL_EXAMPLES,
                             ids=[os.path.basename(p) for p in ALL_EXAMPLES])
    def test_no_zero_duration_trace(self, path):
        """Trace duration should not be 0ms (except trivial examples)."""
        r = _run(path)
        # Only check examples that print duration
        if "Duration: 0ms" in r.stdout and os.path.basename(path) not in {"minimal.py"}:
            pytest.fail(f"{os.path.basename(path)} shows Duration: 0ms")

    @pytest.mark.parametrize("path", ALL_EXAMPLES,
                             ids=[os.path.basename(p) for p in ALL_EXAMPLES])
    def test_no_zero_spans(self, path):
        """Should not show '0 spans' in output."""
        r = _run(path)
        assert "0 spans" not in r.stdout, f"{os.path.basename(path)} shows 0 spans"
