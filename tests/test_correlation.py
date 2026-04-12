"""Tests for span correlation — fingerprints, causal links, patterns."""

import pytest
from datetime import datetime, timezone, timedelta
from agentguard.core.trace import ExecutionTrace, Span, SpanType, SpanStatus
from agentguard.correlation import (
    fingerprint_span, correlate_failures_to_handoffs,
    detect_patterns, analyze_correlations, CorrelationReport,
)


def _ts(offset_s: float = 0) -> str:
    base = datetime(2026, 4, 12, 0, 0, 0, tzinfo=timezone.utc)
    return (base + timedelta(seconds=offset_s)).isoformat()


class TestFingerprint:
    """Tests for span fingerprinting."""

    def test_basic_fingerprint(self):
        """Fingerprint should generate a hash."""
        span = Span(name="test_agent", span_type=SpanType.AGENT, status=SpanStatus.COMPLETED)
        fp = fingerprint_span(span)
        
        assert fp.fingerprint
        assert len(fp.fingerprint) == 16
        assert fp.pattern_key == "agent:test_agent"

    def test_same_structure_same_fingerprint(self):
        """Two spans with same structure should have same fingerprint."""
        s1 = Span(name="agent_a", span_type=SpanType.AGENT, status=SpanStatus.COMPLETED,
                  input_data={"query": "test"}, output_data={"result": "ok"})
        s2 = Span(name="agent_a", span_type=SpanType.AGENT, status=SpanStatus.COMPLETED,
                  input_data={"query": "different"}, output_data={"result": "also ok"})
        
        fp1 = fingerprint_span(s1)
        fp2 = fingerprint_span(s2)
        
        # Same keys → same fingerprint
        assert fp1.fingerprint == fp2.fingerprint

    def test_different_structure_different_fingerprint(self):
        """Different structures should produce different fingerprints."""
        s1 = Span(name="agent_a", span_type=SpanType.AGENT, status=SpanStatus.COMPLETED)
        s2 = Span(name="agent_a", span_type=SpanType.AGENT, status=SpanStatus.FAILED,
                  error="boom")
        
        fp1 = fingerprint_span(s1)
        fp2 = fingerprint_span(s2)
        
        assert fp1.fingerprint != fp2.fingerprint

    def test_parent_context(self):
        """Parent name should affect pattern key."""
        span = Span(name="web_search", span_type=SpanType.TOOL)
        fp = fingerprint_span(span, parent_name="researcher")
        
        assert fp.pattern_key == "researcher/tool:web_search"


class TestFailureHandoffCorrelation:
    """Tests for failure-to-handoff correlation."""

    def test_no_handoffs_no_correlations(self):
        """No handoffs means no correlations."""
        trace = ExecutionTrace(task="simple")
        trace.add_span(Span(name="a", status=SpanStatus.FAILED, error="oops",
                           started_at=_ts(0), ended_at=_ts(1)))
        
        result = correlate_failures_to_handoffs(trace)
        assert result == []

    def test_handoff_before_failure(self):
        """Handoff followed by failure in receiver should be correlated."""
        trace = ExecutionTrace(task="corr_test")
        
        # Handoff span
        h = Span(span_id="h1", name="collector → analyzer", span_type=SpanType.HANDOFF,
                status=SpanStatus.COMPLETED,
                handoff_from="collector", handoff_to="analyzer",
                context_dropped_keys=["raw_data"],
                started_at=_ts(0), ended_at=_ts(1))
        h.metadata["handoff.utilization"] = 0.3
        trace.add_span(h)
        
        # Failed receiver
        trace.add_span(Span(name="analyzer", status=SpanStatus.FAILED,
                           error="Missing required data",
                           started_at=_ts(1), ended_at=_ts(2)))
        
        result = correlate_failures_to_handoffs(trace)
        assert len(result) == 1
        assert result[0].correlation_type == "causal"
        assert result[0].confidence > 0.5  # high confidence due to dropped keys + low utilization


class TestPatternDetection:
    """Tests for recurring pattern detection."""

    def test_repeated_failures(self):
        """Same agent failing multiple times should be detected."""
        trace = ExecutionTrace(task="pattern")
        for i in range(3):
            trace.add_span(Span(name="flaky_agent", status=SpanStatus.FAILED, error=f"fail_{i}",
                              started_at=_ts(i), ended_at=_ts(i + 0.5)))
        
        patterns = detect_patterns(trace)
        repeated = [p for p in patterns if p["type"] == "repeated_failure"]
        assert len(repeated) == 1
        assert repeated[0]["count"] == 3

    def test_slow_agent(self):
        """Agent much slower than average should be flagged."""
        trace = ExecutionTrace(task="slow")
        trace.add_span(Span(name="fast1", span_type=SpanType.AGENT, status=SpanStatus.COMPLETED,
                           started_at=_ts(0), ended_at=_ts(1)))  # 1s
        trace.add_span(Span(name="fast2", span_type=SpanType.AGENT, status=SpanStatus.COMPLETED,
                           started_at=_ts(1), ended_at=_ts(2)))  # 1s
        trace.add_span(Span(name="slowpoke", span_type=SpanType.AGENT, status=SpanStatus.COMPLETED,
                           started_at=_ts(2), ended_at=_ts(12)))  # 10s
        
        patterns = detect_patterns(trace)
        slow = [p for p in patterns if p["type"] == "slow_agent"]
        assert len(slow) == 1
        assert slow[0]["agent"] == "slowpoke"

    def test_retry_storm(self):
        """Many retries should trigger retry_storm pattern."""
        trace = ExecutionTrace(task="retries")
        for i in range(5):
            trace.add_span(Span(name=f"tool_{i}", retry_count=3,
                              started_at=_ts(i), ended_at=_ts(i + 0.5)))
        
        patterns = detect_patterns(trace)
        storm = [p for p in patterns if p["type"] == "retry_storm"]
        assert len(storm) == 1
        assert storm[0]["count"] == 15  # 5 spans × 3 retries


class TestAnalyzeCorrelations:
    """Tests for complete correlation analysis."""

    def test_full_analysis(self):
        """Full analysis should return fingerprints + correlations + patterns."""
        trace = ExecutionTrace(task="full")
        trace.add_span(Span(name="agent_a", span_type=SpanType.AGENT, status=SpanStatus.COMPLETED,
                           started_at=_ts(0), ended_at=_ts(5)))
        trace.add_span(Span(name="agent_b", span_type=SpanType.AGENT, status=SpanStatus.COMPLETED,
                           started_at=_ts(5), ended_at=_ts(10)))
        
        result = analyze_correlations(trace)
        assert isinstance(result, CorrelationReport)
        assert len(result.fingerprints) == 2
        assert isinstance(result.to_dict(), dict)

    def test_report_output(self):
        """Report should be a string."""
        trace = ExecutionTrace(task="report")
        trace.add_span(Span(name="a", status=SpanStatus.COMPLETED))
        
        result = analyze_correlations(trace)
        report = result.to_report()
        assert "Correlation" in report
