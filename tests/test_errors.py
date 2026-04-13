"""Tests for error classification."""

from agentguard.core.trace import ExecutionTrace, Span, SpanStatus
from agentguard.errors import ErrorCategory, analyze_errors, classify_error


class TestClassifyError:
    def test_transient(self):
        assert classify_error("Connection refused") == ErrorCategory.TRANSIENT
        assert classify_error("Request timeout after 30s") == ErrorCategory.TRANSIENT
        assert classify_error("429 Too Many Requests") == ErrorCategory.TRANSIENT
        assert classify_error("Service temporarily unavailable") == ErrorCategory.TRANSIENT

    def test_permanent(self):
        assert classify_error("401 Unauthorized") == ErrorCategory.PERMANENT
        assert classify_error("Resource not found") == ErrorCategory.PERMANENT
        assert classify_error("Invalid API key") == ErrorCategory.PERMANENT

    def test_resource(self):
        assert classify_error("Out of memory") == ErrorCategory.RESOURCE
        assert classify_error("Disk full") == ErrorCategory.RESOURCE
        assert classify_error("Quota exceeded for user") == ErrorCategory.RESOURCE

    def test_logic(self):
        assert classify_error("TypeError: expected str, got int") == ErrorCategory.LOGIC
        assert classify_error("AssertionError: expected True") == ErrorCategory.LOGIC
        assert classify_error("ValueError: invalid literal") == ErrorCategory.LOGIC

    def test_unknown(self):
        assert classify_error("Something weird happened") == ErrorCategory.UNKNOWN
        assert classify_error("") == ErrorCategory.UNKNOWN


class TestAnalyzeErrors:
    def test_mixed_errors(self):
        trace = ExecutionTrace(task="errors")
        trace.add_span(Span(name="a", status=SpanStatus.FAILED, error="Connection timeout"))
        trace.add_span(Span(name="b", status=SpanStatus.FAILED, error="Invalid API key"))
        trace.add_span(Span(name="c", status=SpanStatus.COMPLETED))

        report = analyze_errors(trace)
        assert report.total_errors == 2
        assert report.retryable_count == 1  # only timeout is retryable
        assert "transient" in report.by_category
        assert "permanent" in report.by_category

    def test_no_errors(self):
        trace = ExecutionTrace(task="clean")
        trace.add_span(Span(name="a", status=SpanStatus.COMPLETED))
        report = analyze_errors(trace)
        assert report.total_errors == 0

    def test_report(self):
        trace = ExecutionTrace(task="report")
        trace.add_span(Span(name="a", status=SpanStatus.FAILED, error="Connection refused"))
        report = analyze_errors(trace)
        text = report.to_report()
        assert "transient" in text
