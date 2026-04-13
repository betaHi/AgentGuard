"""Batch trace exporter — accumulate and flush to reduce I/O.

Production traces can complete at high rates. Writing each trace
individually creates I/O pressure. The BatchExporter accumulates
completed traces and writes them in batches.

Usage:
    exporter = BatchExporter(output_dir="./traces", batch_size=10)
    exporter.add(trace)  # queued
    exporter.add(trace)  # queued
    exporter.flush()     # writes all queued traces

    # Or use auto-flush:
    exporter = BatchExporter(batch_size=5)
    for trace in traces:
        exporter.add(trace)  # auto-flushes every 5 traces
"""

from __future__ import annotations

import contextlib
import json
import logging
import threading
import time
from collections.abc import Callable
from pathlib import Path

from agentguard.core.trace import ExecutionTrace

_logger = logging.getLogger(__name__)


class BatchExporter:
    """Accumulates traces and flushes them in batches.

    Thread-safe: multiple threads can add traces concurrently.

    Args:
        output_dir: Directory to write batch files.
        batch_size: Number of traces to accumulate before auto-flush.
        max_age_seconds: Max seconds before auto-flush (0 = disabled).
        on_flush: Optional callback invoked with list of traces on flush.
    """

    def __init__(
        self,
        output_dir: str = ".agentguard/traces",
        batch_size: int = 10,
        max_age_seconds: float = 0,
        on_flush: Callable[[list[ExecutionTrace]], None] | None = None,
    ):
        self._output_dir = Path(output_dir)
        self._batch_size = max(1, batch_size)
        self._max_age = max_age_seconds
        self._on_flush = on_flush
        self._buffer: list[ExecutionTrace] = []
        self._lock = threading.Lock()
        self._first_add_time: float | None = None
        self._flush_count = 0

    @property
    def pending(self) -> int:
        """Number of traces waiting to be flushed."""
        with self._lock:
            return len(self._buffer)

    @property
    def flush_count(self) -> int:
        """Total number of flushes performed."""
        return self._flush_count

    def add(self, trace: ExecutionTrace) -> None:
        """Add a completed trace to the batch buffer.

        Auto-flushes when batch_size is reached or max_age exceeded.

        Args:
            trace: A completed ExecutionTrace.
        """
        should_flush = False
        with self._lock:
            self._buffer.append(trace)
            if self._first_add_time is None:
                self._first_add_time = time.monotonic()
            if len(self._buffer) >= self._batch_size:
                should_flush = True
            elif self._max_age > 0 and self._first_add_time:
                age = time.monotonic() - self._first_add_time
                if age >= self._max_age:
                    should_flush = True
        if should_flush:
            self.flush()

    def flush(self) -> list[ExecutionTrace]:
        """Flush all buffered traces.

        Writes to disk and/or invokes on_flush callback.

        Returns:
            List of traces that were flushed.
        """
        with self._lock:
            batch = self._buffer[:]
            self._buffer.clear()
            self._first_add_time = None

        if not batch:
            return []

        self._flush_count += 1

        if self._on_flush:
            self._on_flush(batch)
        else:
            self._write_batch(batch)

        _logger.debug("Flushed %d traces (batch #%d)", len(batch), self._flush_count)
        return batch

    def _write_batch(self, batch: list[ExecutionTrace]) -> None:
        """Write a batch of traces to a single JSON file."""
        self._output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = int(time.time() * 1000)
        path = self._output_dir / f"batch_{timestamp}_{self._flush_count}.json"
        data = [t.to_dict() for t in batch]
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        _logger.debug("Wrote batch to %s", path)

    def __del__(self):
        """Flush remaining traces on garbage collection."""
        if self._buffer:
            with contextlib.suppress(Exception):
                self.flush()
