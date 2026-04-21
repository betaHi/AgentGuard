"""Tests for thread safety of the SDK and recorder."""

import threading
import time

from agentguard import (
    TraceThread,
    disable_auto_trace_threading,
    enable_auto_trace_threading,
    is_auto_trace_threading_enabled,
    record_agent,
    record_handoff,
    record_tool,
)
from agentguard.core.trace import SpanType
from agentguard.sdk.recorder import finish_recording, init_recorder


class TestThreadSafety:
    """Verify SDK works correctly with concurrent threads."""

    def test_parallel_agents_recorded(self):
        """Multiple agents running in parallel should all be captured."""
        init_recorder(task="thread_test")

        results = {}

        @record_agent(name="worker_a")
        def worker_a():
            time.sleep(0.05)
            return {"from": "a"}

        @record_agent(name="worker_b")
        def worker_b():
            time.sleep(0.05)
            return {"from": "b"}

        @record_agent(name="worker_c")
        def worker_c():
            time.sleep(0.05)
            return {"from": "c"}

        def run(name, fn):
            results[name] = fn()

        threads = [
            threading.Thread(target=run, args=("a", worker_a)),
            threading.Thread(target=run, args=("b", worker_b)),
            threading.Thread(target=run, args=("c", worker_c)),
        ]

        for t in threads: t.start()
        for t in threads: t.join()

        trace = finish_recording()

        # All 3 agents should be recorded
        agent_names = {s.name for s in trace.spans if s.span_type == SpanType.AGENT}
        assert "worker_a" in agent_names
        assert "worker_b" in agent_names
        assert "worker_c" in agent_names

    def test_parallel_tools_recorded(self):
        """Tools called from parallel agents should be captured."""
        init_recorder(task="tool_thread_test")

        @record_tool(name="fetch")
        def fetch(url):
            time.sleep(0.02)
            return {"data": url}

        @record_agent(name="fetcher_1")
        def fetcher_1():
            return fetch("url_1")

        @record_agent(name="fetcher_2")
        def fetcher_2():
            return fetch("url_2")

        threads = [
            threading.Thread(target=fetcher_1),
            threading.Thread(target=fetcher_2),
        ]

        for t in threads: t.start()
        for t in threads: t.join()

        trace = finish_recording()

        # Both agents and their tools should be recorded
        assert len(trace.spans) >= 4  # 2 agents + 2 tools

    def test_handoff_with_threading(self):
        """Handoffs should work alongside threaded agents."""
        init_recorder(task="handoff_thread_test")

        @record_agent(name="sender")
        def sender():
            return {"data": "hello"}

        @record_agent(name="receiver")
        def receiver(data):
            return {"processed": True}

        result = sender()
        record_handoff("sender", "receiver", context=result)
        receiver(result)

        trace = finish_recording()

        handoffs = [s for s in trace.spans if s.span_type == SpanType.HANDOFF]
        assert len(handoffs) >= 1

    def test_many_concurrent_spans(self):
        """Stress test: 20 concurrent agents."""
        init_recorder(task="stress_test")

        @record_agent(name="stress_worker")
        def stress_worker(i):
            time.sleep(0.01)
            return {"index": i}

        threads = [
            threading.Thread(target=stress_worker, args=(i,))
            for i in range(20)
        ]

        for t in threads: t.start()
        for t in threads: t.join()

        trace = finish_recording()
        assert len(trace.spans) >= 20

    def test_trace_thread_preserves_parent_child_topology(self):
        """Child threads should inherit the coordinator span as parent."""
        init_recorder(task="thread_topology_test")

        @record_agent(name="worker")
        def worker(label):
            time.sleep(0.01)
            return {"label": label}

        @record_agent(name="coordinator")
        def coordinator():
            threads = [
                TraceThread(target=worker, args=("a",)),
                TraceThread(target=worker, args=("b",)),
                TraceThread(target=worker, args=("c",)),
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

        coordinator()
        trace = finish_recording()

        roots = [span for span in trace.spans if span.parent_span_id is None]
        assert len(roots) == 1
        assert roots[0].name == "coordinator"

        workers = [span for span in trace.spans if span.name == "worker"]
        assert len(workers) == 3
        assert all(span.parent_span_id == roots[0].span_id for span in workers)

    def test_auto_threading_preserves_parent_child_topology(self):
        """Standard threads should inherit parent context when auto mode is on."""
        enable_auto_trace_threading()
        try:
            init_recorder(task="auto_thread_topology_test")

            @record_agent(name="worker")
            def worker(label):
                time.sleep(0.01)
                return {"label": label}

            @record_agent(name="coordinator")
            def coordinator():
                threads = [
                    threading.Thread(target=worker, args=("a",)),
                    threading.Thread(target=worker, args=("b",)),
                    threading.Thread(target=worker, args=("c",)),
                ]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join()

            coordinator()
            trace = finish_recording()

            roots = [span for span in trace.spans if span.parent_span_id is None]
            workers = [span for span in trace.spans if span.name == "worker"]
            assert len(roots) == 1
            assert roots[0].name == "coordinator"
            assert len(workers) == 3
            assert all(span.parent_span_id == roots[0].span_id for span in workers)
        finally:
            disable_auto_trace_threading()

    def test_disable_auto_threading_restores_default_behavior(self):
        """Disabling auto mode should restore standard thread isolation."""
        enable_auto_trace_threading()
        disable_auto_trace_threading()
        assert not is_auto_trace_threading_enabled()

        init_recorder(task="auto_thread_disabled_test")

        @record_agent(name="worker")
        def worker(label):
            time.sleep(0.01)
            return {"label": label}

        @record_agent(name="coordinator")
        def coordinator():
            threads = [
                threading.Thread(target=worker, args=("a",)),
                threading.Thread(target=worker, args=("b",)),
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

        coordinator()
        trace = finish_recording()

        roots = [span for span in trace.spans if span.parent_span_id is None]
        workers = [span for span in trace.spans if span.name == "worker"]
        assert len(workers) == 2
        assert len(roots) == 3
        assert any(span.name == "coordinator" for span in roots)

    def test_enable_auto_threading_is_idempotent(self):
        """Repeated enable/disable calls should be safe."""
        enable_auto_trace_threading()
        enable_auto_trace_threading()
        assert is_auto_trace_threading_enabled()
        disable_auto_trace_threading()
        disable_auto_trace_threading()
        assert not is_auto_trace_threading_enabled()

