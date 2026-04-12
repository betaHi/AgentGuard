"""Tests for thread safety of the SDK and recorder."""

import pytest
import threading
import time
from agentguard import TraceThread, record_agent, record_tool, record_handoff
from agentguard.sdk.recorder import init_recorder, finish_recording, get_recorder
from agentguard.core.trace import SpanType, SpanStatus


class TestThreadSafety:
    """Verify SDK works correctly with concurrent threads."""
    
    def test_parallel_agents_recorded(self):
        """Multiple agents running in parallel should all be captured."""
        recorder = init_recorder(task="thread_test")
        
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
        recorder = init_recorder(task="tool_thread_test")
        
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
        recorder = init_recorder(task="handoff_thread_test")
        
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
        recorder = init_recorder(task="stress_test")
        
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

