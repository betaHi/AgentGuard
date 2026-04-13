"""Tests for SDK batch trace exporter."""

import json
import os
import tempfile

from agentguard.builder import TraceBuilder
from agentguard.sdk.exporter import BatchExporter


def _trace(name="t"):
    return TraceBuilder(name).agent("a", duration_ms=100).end().build()


class TestBatchExporter:
    def test_add_and_pending(self):
        ex = BatchExporter(batch_size=10)
        ex.add(_trace())
        assert ex.pending == 1

    def test_auto_flush_at_batch_size(self):
        flushed = []
        ex = BatchExporter(batch_size=3, on_flush=lambda b: flushed.extend(b))
        ex.add(_trace("1"))
        ex.add(_trace("2"))
        assert ex.pending == 2
        ex.add(_trace("3"))  # triggers flush
        assert ex.pending == 0
        assert len(flushed) == 3

    def test_manual_flush(self):
        flushed = []
        ex = BatchExporter(batch_size=100, on_flush=lambda b: flushed.extend(b))
        ex.add(_trace())
        ex.add(_trace())
        result = ex.flush()
        assert len(result) == 2
        assert len(flushed) == 2
        assert ex.pending == 0

    def test_flush_empty_returns_empty(self):
        ex = BatchExporter(batch_size=10, on_flush=lambda b: None)
        result = ex.flush()
        assert result == []

    def test_flush_count(self):
        ex = BatchExporter(batch_size=2, on_flush=lambda b: None)
        ex.add(_trace())
        ex.add(_trace())  # auto-flush
        ex.add(_trace())
        ex.flush()  # manual flush
        assert ex.flush_count == 2

    def test_write_to_disk(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ex = BatchExporter(output_dir=tmpdir, batch_size=2)
            ex.add(_trace("a"))
            ex.add(_trace("b"))  # auto-flush writes file
            files = os.listdir(tmpdir)
            assert len(files) == 1
            data = json.loads(open(os.path.join(tmpdir, files[0])).read())
            assert len(data) == 2
            assert data[0]["task"] == "a"

    def test_thread_safety(self):
        import threading
        flushed = []
        lock = threading.Lock()

        def on_flush(batch):
            with lock:
                flushed.extend(batch)

        ex = BatchExporter(batch_size=5, on_flush=on_flush)
        threads = []
        for _i in range(20):
            t = threading.Thread(target=lambda: ex.add(_trace()))
            threads.append(t)
            t.start()
        for t in threads:
            t.join()
        ex.flush()  # flush remaining
        assert len(flushed) == 20

    def test_on_flush_callback(self):
        tasks = []
        ex = BatchExporter(batch_size=2, on_flush=lambda b: tasks.extend(t.task for t in b))
        ex.add(_trace("x"))
        ex.add(_trace("y"))
        assert tasks == ["x", "y"]

    def test_batch_size_one(self):
        """batch_size=1 flushes immediately."""
        flushed = []
        ex = BatchExporter(batch_size=1, on_flush=lambda b: flushed.extend(b))
        ex.add(_trace())
        assert len(flushed) == 1
        assert ex.pending == 0
