"""Test: concurrent recording from multiple threads simultaneously.

The SDK recorder uses threading.local for span stacks. This test
verifies that concurrent threads don't corrupt each other's traces.
"""

import threading
import time

from agentguard.sdk.decorators import record_agent, record_tool
from agentguard.sdk.recorder import get_recorder


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
