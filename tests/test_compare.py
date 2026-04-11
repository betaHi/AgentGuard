"""Tests for comparison and regression detection."""

from agentguard.core.trace import ExecutionTrace, Span, SpanType, SpanStatus
from agentguard.core.eval_schema import EvaluationResult, RuleResult, RuleVerdict
from agentguard.eval.compare import compare_traces, compare_evals, ComparisonResult


def test_compare_traces_basic():
    """Compare two traces detects differences."""
    t1 = ExecutionTrace(task="test")
    s1 = Span(name="agent", span_type=SpanType.AGENT)
    s1.complete()
    t1.add_span(s1)
    t1.complete()
    
    t2 = ExecutionTrace(task="test")
    s2 = Span(name="agent", span_type=SpanType.AGENT)
    s2.fail("error")
    t2.add_span(s2)
    t2.fail()
    
    result = compare_traces(t1, t2)
    assert any(d.field == "error_count" for d in result.diffs)
    error_diff = [d for d in result.diffs if d.field == "error_count"][0]
    assert error_diff.verdict == "regressed"


def test_compare_evals():
    """Compare two evaluation results."""
    e1 = EvaluationResult(trace_id="t1", agent_name="a", agent_version="v1")
    e1.rules = [
        RuleResult(name="check1", rule_type="min_count", verdict=RuleVerdict.PASS),
        RuleResult(name="check2", rule_type="each_has", verdict=RuleVerdict.FAIL),
    ]
    
    e2 = EvaluationResult(trace_id="t2", agent_name="a", agent_version="v2")
    e2.rules = [
        RuleResult(name="check1", rule_type="min_count", verdict=RuleVerdict.PASS),
        RuleResult(name="check2", rule_type="each_has", verdict=RuleVerdict.PASS),
    ]
    
    result = compare_evals(e1, e2)
    assert result.improved >= 1
    assert result.recommendation == "safe_to_deploy"


def test_comparison_report():
    """Comparison result generates readable report."""
    result = ComparisonResult(
        baseline_id="t1", candidate_id="t2",
        baseline_version="v1", candidate_version="v2"
    )
    report = result.to_report()
    assert "Regression Report" in report
