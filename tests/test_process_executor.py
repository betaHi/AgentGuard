"""Tests for TracingProcessExecutor — multiprocessing trace propagation."""

import time

from agentguard import record_agent
from agentguard.sdk.context import TracingProcessExecutor
from agentguard.sdk.recorder import finish_recording, init_recorder


def _cpu_work(n):
    """Simple picklable function for worker processes."""
    return sum(range(n))


@record_agent(name="process_agent", version="v1")
def _recorded_work(n):
    """Agent that creates spans in worker process."""
    time.sleep(0.01)
    return n * 2


class TestTracingProcessExecutor:
    def test_basic_submit_returns_result(self):
        """submit() returns correct result via MergingFuture."""
        init_recorder(task="proc test", trigger="test")
        with TracingProcessExecutor(max_workers=1) as ex:
            future = ex.submit(_cpu_work, 100)
            result = future.result(timeout=10)
        finish_recording()
        assert result == sum(range(100))

    def test_multiple_submits(self):
        """Multiple concurrent submits all return correct results."""
        init_recorder(task="proc multi", trigger="test")
        with TracingProcessExecutor(max_workers=2) as ex:
            futures = [ex.submit(_cpu_work, i * 10) for i in range(3)]
            results = [f.result(timeout=10) for f in futures]
        finish_recording()
        assert results == [sum(range(i * 10)) for i in range(3)]

    def test_worker_spans_merged(self):
        """Spans created in worker process are merged into parent trace."""
        init_recorder(task="proc spans", trigger="test")
        with TracingProcessExecutor(max_workers=1) as ex:
            future = ex.submit(_recorded_work, 5)
            result = future.result(timeout=10)
        trace = finish_recording()
        assert result == 10
        agent_names = [s.name for s in trace.agent_spans]
        assert "process_agent" in agent_names

    def test_context_manager(self):
        """Works as context manager (enter/exit)."""
        init_recorder(task="ctx", trigger="test")
        with TracingProcessExecutor(max_workers=1) as ex:
            f = ex.submit(_cpu_work, 5)
            assert f.result(timeout=10) == 10
        finish_recording()

    def test_future_done(self):
        """MergingFuture.done() works."""
        init_recorder(task="done", trigger="test")
        with TracingProcessExecutor(max_workers=1) as ex:
            f = ex.submit(_cpu_work, 5)
            f.result(timeout=10)
            assert f.done()
        finish_recording()
