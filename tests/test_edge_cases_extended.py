"""Extended edge case tests — stress test all modules with unusual inputs."""

from datetime import UTC, datetime, timedelta

from agentguard.core.trace import ExecutionTrace, Span, SpanStatus, SpanType


def _ts(offset_s: float = 0) -> str:
    base = datetime(2026, 4, 12, 0, 0, 0, tzinfo=UTC)
    return (base + timedelta(seconds=offset_s)).isoformat()


class TestEmptyTrace:
    """All modules should handle empty traces gracefully."""

    def test_scoring(self):
        from agentguard.scoring import score_trace
        score = score_trace(ExecutionTrace(task="empty"))
        assert score.overall >= 0

    def test_metrics(self):
        from agentguard.metrics import extract_metrics
        m = extract_metrics(ExecutionTrace())
        assert m.span_count == 0

    def test_timeline(self):
        from agentguard.timeline import build_timeline
        tl = build_timeline(ExecutionTrace())
        assert tl.events == []

    def test_flow_graph(self):
        from agentguard.flowgraph import build_flow_graph
        g = build_flow_graph(ExecutionTrace())
        assert g.nodes == []

    def test_propagation(self):
        from agentguard.propagation import analyze_propagation
        r = analyze_propagation(ExecutionTrace())
        assert r.total_failures == 0

    def test_context_flow(self):
        from agentguard.context_flow import analyze_context_flow_deep
        r = analyze_context_flow_deep(ExecutionTrace())
        assert len(r.transitions) == 0

    def test_correlations(self):
        from agentguard.correlation import analyze_correlations
        r = analyze_correlations(ExecutionTrace())
        assert r.fingerprints == []

    def test_annotations(self):
        from agentguard.annotations import auto_annotate
        store = auto_annotate(ExecutionTrace())
        assert store.count == 0

    def test_tree(self):
        from agentguard.tree import compute_tree_stats
        s = compute_tree_stats(ExecutionTrace())
        assert s.node_count == 0

    def test_normalize(self):
        from agentguard.normalize import normalize_trace
        r = normalize_trace(ExecutionTrace())
        assert isinstance(r.changes, list)

    def test_summarize(self):
        from agentguard.summarize import summarize_trace
        s = summarize_trace(ExecutionTrace())
        assert len(s) > 0

    def test_schema(self):
        from agentguard.schema import validate_trace_dict
        errors = validate_trace_dict(ExecutionTrace().to_dict())
        assert errors == []

    def test_aggregate(self):
        from agentguard.aggregate import aggregate_traces
        r = aggregate_traces([])
        assert r.trace_count == 0

    def test_profiles(self):
        from agentguard.profile import build_agent_profiles
        p = build_agent_profiles([])
        assert p == {}


class TestLargeTrace:
    """Test with a large number of spans."""

    def test_100_spans(self):
        from agentguard.metrics import extract_metrics
        from agentguard.scoring import score_trace
        from agentguard.tree import compute_tree_stats

        trace = ExecutionTrace(task="large", started_at=_ts(0), ended_at=_ts(200))
        for i in range(100):
            trace.add_span(Span(
                name=f"agent_{i}", span_type=SpanType.AGENT,
                status=SpanStatus.COMPLETED if i % 5 != 0 else SpanStatus.FAILED,
                error="periodic failure" if i % 5 == 0 else None,
                started_at=_ts(i * 2), ended_at=_ts(i * 2 + 1),
                token_count=100, estimated_cost_usd=0.001,
            ))

        score = score_trace(trace)
        assert score.overall > 0

        m = extract_metrics(trace)
        assert m.span_count == 100
        assert m.total_tokens == 10000

        stats = compute_tree_stats(trace)
        assert stats.node_count == 100

    def test_deep_nesting(self):
        """50-level deep nesting should not stack overflow."""
        from agentguard.tree import compute_tree_stats, tree_to_text

        trace = ExecutionTrace(task="deep")
        parent_id = None
        for i in range(50):
            span = Span(span_id=f"s{i}", name=f"level_{i}", parent_span_id=parent_id)
            trace.add_span(span)
            parent_id = span.span_id

        stats = compute_tree_stats(trace)
        assert stats.depth == 50
        text = tree_to_text(trace)
        assert "level_0" in text


class TestMalformedTrace:
    """Test with malformed/unexpected data."""

    def test_none_timestamps(self):
        from agentguard.timeline import build_timeline
        trace = ExecutionTrace(task="no_times")
        trace.add_span(Span(name="a", started_at="", ended_at=""))
        build_timeline(trace)
        # Should not crash

    def test_duplicate_span_ids(self):
        from agentguard.normalize import normalize_trace
        trace = ExecutionTrace(task="dup")
        trace.spans = [
            Span(span_id="dup", name="first"),
            Span(span_id="dup", name="second"),
        ]
        normalize_trace(trace)
        assert len(trace.spans) == 1  # deduplicated

    def test_circular_parent(self):
        from agentguard.tree import detect_cycles
        trace = ExecutionTrace(task="cycle")
        trace.add_span(Span(span_id="a", name="a", parent_span_id="b"))
        trace.add_span(Span(span_id="b", name="b", parent_span_id="a"))
        cycles = detect_cycles(trace)
        assert len(cycles) >= 1

    def test_unicode_names(self):
        from agentguard.scoring import score_trace
        trace = ExecutionTrace(task="Unicode: 🤖🦐")
        trace.add_span(Span(name="エージェント", status=SpanStatus.COMPLETED))
        score = score_trace(trace)
        assert score.overall >= 0

    def test_huge_metadata(self):
        from agentguard.metrics import extract_metrics
        trace = ExecutionTrace(task="big_meta")
        trace.add_span(Span(name="a", metadata={"key": "x" * 10000}))
        m = extract_metrics(trace)
        assert m.span_count == 1
