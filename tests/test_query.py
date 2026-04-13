"""Tests for trace query utilities."""

import tempfile
from pathlib import Path

from agentguard.core.trace import ExecutionTrace, Span, SpanType
from agentguard.query import TraceStore


def _write_traces(traces_dir: Path, traces: list[ExecutionTrace]):
    traces_dir.mkdir(parents=True, exist_ok=True)
    for t in traces:
        (traces_dir / f"{t.trace_id}.json").write_text(t.to_json())


def _make_traces():
    traces = []

    # Successful trace
    t1 = ExecutionTrace(task="Daily Report", trigger="cron")
    a1 = Span(name="researcher", span_type=SpanType.AGENT)
    a1.complete()
    t1.add_span(a1)
    t1.complete()
    traces.append(t1)

    # Failed trace
    t2 = ExecutionTrace(task="Research Pipeline", trigger="manual")
    a2 = Span(name="researcher", span_type=SpanType.AGENT)
    a2.fail("timeout")
    t2.add_span(a2)
    t2.fail()
    traces.append(t2)

    return traces


def test_filter_by_status():
    with tempfile.TemporaryDirectory() as tmpdir:
        traces_dir = Path(tmpdir) / "traces"
        _write_traces(traces_dir, _make_traces())

        store = TraceStore(str(traces_dir))
        failed = store.filter(status="failed")
        assert len(failed) == 1
        assert failed[0].task == "Research Pipeline"


def test_filter_by_agent():
    with tempfile.TemporaryDirectory() as tmpdir:
        traces_dir = Path(tmpdir) / "traces"
        _write_traces(traces_dir, _make_traces())

        store = TraceStore(str(traces_dir))
        with_researcher = store.filter(agent_name="researcher")
        assert len(with_researcher) == 2


def test_filter_has_errors():
    with tempfile.TemporaryDirectory() as tmpdir:
        traces_dir = Path(tmpdir) / "traces"
        _write_traces(traces_dir, _make_traces())

        store = TraceStore(str(traces_dir))
        errored = store.filter(has_errors=True)
        assert len(errored) == 1


def test_agent_stats():
    with tempfile.TemporaryDirectory() as tmpdir:
        traces_dir = Path(tmpdir) / "traces"
        _write_traces(traces_dir, _make_traces())

        store = TraceStore(str(traces_dir))
        stats = store.agent_stats()
        assert "researcher" in stats
        assert stats["researcher"]["executions"] == 2
        assert stats["researcher"]["success_rate"] == 0.5
