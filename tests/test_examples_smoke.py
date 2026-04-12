"""Smoke tests for all examples — verify they run without crashing."""

import pytest
import subprocess
import sys
import os

EXAMPLES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "examples")


def _run_example(name, timeout=30):
    """Run an example script and return (exit_code, stdout, stderr)."""
    path = os.path.join(EXAMPLES_DIR, name)
    if not os.path.exists(path):
        pytest.skip(f"{name} not found")
    
    result = subprocess.run(
        [sys.executable, path],
        capture_output=True, text=True, timeout=timeout,
        cwd=os.path.dirname(EXAMPLES_DIR),
    )
    return result


class TestExamplesSmoke:
    """Each example should run without errors."""
    
    def test_parallel_pipeline(self):
        result = _run_example("parallel_pipeline.py")
        assert result.returncode == 0, f"Error: {result.stderr}"
        assert "Score" in result.stdout

    def test_parallel_coding(self):
        result = _run_example("parallel_coding.py")
        assert result.returncode == 0, f"Error: {result.stderr}"
        assert "Score" in result.stdout

    def test_production_usage(self):
        result = _run_example("production_usage.py")
        assert result.returncode == 0, f"Error: {result.stderr}"
        assert "Score" in result.stdout

    def test_error_recovery(self):
        result = _run_example("error_recovery.py")
        assert result.returncode == 0, f"Error: {result.stderr}"
        assert "Score" in result.stdout

    def test_coding_pipeline(self):
        result = _run_example("coding_pipeline.py")
        assert result.returncode == 0, f"Error: {result.stderr}"

    def test_deep_analysis_demo(self):
        result = _run_example("deep_analysis_demo.py")
        assert result.returncode == 0, f"Error: {result.stderr}"

    def test_full_analysis(self):
        result = _run_example("full_analysis.py")
        assert result.returncode == 0, f"Error: {result.stderr}"
