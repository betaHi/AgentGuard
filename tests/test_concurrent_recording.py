"""Test: concurrent recording from multiple threads simultaneously.

The SDK recorder uses threading.local for span stacks. This test
verifies that concurrent threads don't corrupt each other's traces.
"""

import threading
import time
from pathlib import Path

from agentguard.core.trace import Span, SpanType
from agentguard.sdk.decorators import record_agent, record_tool
from agentguard.sdk.recorder import TraceRecorder, get_recorder


class TestConcurrentRecording:
    def test_threads_have_isolated_stacks(self):
        """Each thread maintains its own independent span stack."""
        errors = []

        def worker(thread_id):
            try:
                recorder = get_recorder()
                # Each thread should start with empty stack
                assert recorder.current_span_id is None, (
                    f"Thread {thread_id}: non-empty initial stack"
                )
                # Push a span, verify other threads don't see it
                from agentguard.core.trace import Span, SpanType
                span = Span(span_type=SpanType.AGENT, name=f"t{thread_id}")
                recorder.push_span(span)
                time.sleep(0.02)
                assert recorder.current_span_id == span.span_id, (
                    f"Thread {thread_id}: stack corrupted by another thread"
                )
                recorder.pop_span(span)
            except Exception as e:
                errors.append(f"Thread {thread_id}: {e}")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Thread errors: {errors}"

    def test_decorated_functions_concurrent(self):
        """Decorated functions work correctly under concurrent execution."""
        results = {}
        errors = []

        @record_agent(name="worker")
        def do_work(n):
            time.sleep(0.01)  # simulate work
            return n * 2

        def runner(thread_id):
            try:
                result = do_work(thread_id)
                results[thread_id] = result
            except Exception as e:
                errors.append(f"Thread {thread_id}: {e}")

        threads = [threading.Thread(target=runner, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors: {errors}"
        assert len(results) == 20
        for i in range(20):
            assert results[i] == i * 2

    def test_nested_decorators_concurrent(self):
        """Nested agent+tool decorators are thread-safe."""
        results = {}
        errors = []

        @record_tool(name="compute")
        def compute(x):
            return x + 1

        @record_agent(name="orchestrator")
        def orchestrate(n):
            return compute(n)

        def runner(tid):
            try:
                results[tid] = orchestrate(tid * 10)
            except Exception as e:
                errors.append(f"Thread {tid}: {e}")

        threads = [threading.Thread(target=runner, args=(i,)) for i in range(15)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        for i in range(15):
            assert results[i] == i * 10 + 1

    def test_exception_in_one_thread_doesnt_affect_others(self):
        """A failing decorated function in one thread doesn't break others."""
        results = {}
        errors = []

        @record_agent(name="maybe-fail")
        def maybe_fail(n):
            if n == 5:
                raise ValueError("intentional")
            return n

        def runner(tid):
            try:
                results[tid] = maybe_fail(tid)
            except ValueError:
                results[tid] = "failed"
            except Exception as e:
                errors.append(f"Thread {tid}: {e}")

        threads = [threading.Thread(target=runner, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert results[5] == "failed"
        for i in range(10):
            if i != 5:
                assert results[i] == i

    def test_high_concurrency_stress(self):
        """50 threads recording simultaneously without deadlock."""
        count = {"done": 0}
        lock = threading.Lock()

        @record_agent(name="stress-agent")
        def stress_fn(n):
            return n

        def runner(tid):
            stress_fn(tid)
            with lock:
                count["done"] += 1

        threads = [threading.Thread(target=runner, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert count["done"] == 50

    def test_fifty_threads_record_separate_traces_without_leakage(self, tmp_path):
        """50 threads recording separate traces should not leak spans across traces."""
        trace_dir = Path(tmp_path) / "isolated-traces"
        barrier = threading.Barrier(50)
        traces = {}
        errors = []
        lock = threading.Lock()

        def worker(thread_id):
            try:
                recorder = TraceRecorder(task=f"thread-{thread_id}", output_dir=str(trace_dir))
                barrier.wait(timeout=10)

                agent = Span(span_type=SpanType.AGENT, name=f"agent-{thread_id}")
                recorder.push_span(agent)

                tool = Span(
                    span_type=SpanType.TOOL,
                    name=f"tool-{thread_id}",
                    parent_span_id=agent.span_id,
                )
                recorder.push_span(tool)
                time.sleep(0.01)
                tool.complete({"thread": thread_id})
                recorder.pop_span(tool)

                agent.complete({"thread": thread_id, "status": "done"})
                recorder.pop_span(agent)
                trace = recorder.finish()

                with lock:
                    traces[thread_id] = trace
            except Exception as exc:
                with lock:
                    errors.append(f"thread {thread_id}: {exc}")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(50)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=15)

        assert not errors, f"Errors: {errors}"
        assert len(traces) == 50
        assert len(list(trace_dir.glob("*.json"))) == 50

        for thread_id, trace in traces.items():
            names = {span.name for span in trace.spans}
            assert names == {f"agent-{thread_id}", f"tool-{thread_id}"}
            tool_spans = [span for span in trace.spans if span.name == f"tool-{thread_id}"]
            assert len(tool_spans) == 1
            assert tool_spans[0].parent_span_id is not None
