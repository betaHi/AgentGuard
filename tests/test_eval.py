"""Tests for evaluation engine."""

from datetime import UTC, datetime

from agentguard.core.eval_schema import EvaluationResult, RuleResult, RuleVerdict
from agentguard.eval.rules import (
    _resolve_path,
    eval_contains,
    eval_each_has,
    eval_min_count,
    eval_no_duplicates,
    eval_range,
    eval_recency,
    eval_regex,
    evaluate_rules,
)

# --- Path resolution ---

def test_resolve_path_simple():
    assert _resolve_path({"a": 1}, "a") == 1

def test_resolve_path_nested():
    assert _resolve_path({"a": {"b": 2}}, "a.b") == 2

def test_resolve_path_list():
    data = [{"x": 1}, {"x": 2}, {"x": 3}]
    assert _resolve_path(data, "x") == [1, 2, 3]


# --- min_count ---

def test_min_count_pass():
    data = {"articles": [1, 2, 3, 4, 5]}
    r = eval_min_count(data, target="articles", value=3)
    assert r.verdict == RuleVerdict.PASS

def test_min_count_fail():
    data = {"articles": [1, 2]}
    r = eval_min_count(data, target="articles", value=5)
    assert r.verdict == RuleVerdict.FAIL


# --- each_has ---

def test_each_has_pass():
    data = {"items": [{"title": "A", "url": "http"}, {"title": "B", "url": "http"}]}
    r = eval_each_has(data, target="items", fields=["title", "url"])
    assert r.verdict == RuleVerdict.PASS

def test_each_has_fail():
    data = {"items": [{"title": "A"}, {"title": "B", "url": "http"}]}
    r = eval_each_has(data, target="items", fields=["title", "url"])
    assert r.verdict == RuleVerdict.FAIL


# --- recency ---

def test_recency_pass():
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    data = {"dates": [today, today]}
    r = eval_recency(data, target="dates", within_days=2)
    assert r.verdict == RuleVerdict.PASS

def test_recency_fail():
    old_date = "2020-01-01"
    data = {"dates": [old_date]}
    r = eval_recency(data, target="dates", within_days=2)
    assert r.verdict == RuleVerdict.FAIL


# --- no_duplicates ---

def test_no_duplicates_pass():
    data = {"urls": ["http://a.com", "http://b.com", "http://c.com"]}
    r = eval_no_duplicates(data, target="urls")
    assert r.verdict == RuleVerdict.PASS

def test_no_duplicates_fail():
    data = {"urls": ["http://a.com", "http://b.com", "http://a.com"]}
    r = eval_no_duplicates(data, target="urls")
    assert r.verdict == RuleVerdict.FAIL


# --- contains ---

def test_contains_any_pass():
    data = {"text": "The AI agent framework is great"}
    r = eval_contains(data, target="text", keywords=["agent", "robot"], mode="any")
    assert r.verdict == RuleVerdict.PASS

def test_contains_all_fail():
    data = {"text": "The AI agent framework is great"}
    r = eval_contains(data, target="text", keywords=["agent", "robot"], mode="all")
    assert r.verdict == RuleVerdict.FAIL


# --- regex ---

def test_regex_pass():
    data = {"output": "Total: 42 items found"}
    r = eval_regex(data, target="output", pattern=r"\d+ items")
    assert r.verdict == RuleVerdict.PASS

def test_regex_fail():
    data = {"output": "No results"}
    r = eval_regex(data, target="output", pattern=r"\d+ items")
    assert r.verdict == RuleVerdict.FAIL


# --- range ---

def test_range_pass():
    data = {"score": 0.85}
    r = eval_range(data, target="score", min_val=0.0, max_val=1.0)
    assert r.verdict == RuleVerdict.PASS

def test_range_fail():
    data = {"score": 1.5}
    r = eval_range(data, target="score", min_val=0.0, max_val=1.0)
    assert r.verdict == RuleVerdict.FAIL


# --- evaluate_rules batch ---

def test_evaluate_rules_batch():
    data = {"articles": [
        {"title": "AI News", "url": "http://a.com", "date": datetime.now(UTC).strftime("%Y-%m-%d")},
        {"title": "ML Update", "url": "http://b.com", "date": datetime.now(UTC).strftime("%Y-%m-%d")},
    ]}
    rules = [
        {"type": "min_count", "target": "articles", "value": 2},
        {"type": "each_has", "target": "articles", "fields": ["title", "url", "date"]},
        {"type": "no_duplicates", "target": "articles", "field": "url"},
    ]
    results = evaluate_rules(data, rules)
    assert len(results) == 3
    assert all(r.verdict == RuleVerdict.PASS for r in results)


# --- EvaluationResult ---

def test_evaluation_result_report():
    er = EvaluationResult(trace_id="test", agent_name="my-agent", agent_version="v1")
    er.rules = [
        RuleResult(name="check1", rule_type="min_count", verdict=RuleVerdict.PASS),
        RuleResult(name="check2", rule_type="each_has", verdict=RuleVerdict.FAIL,
                   expected="all fields", actual="missing url", detail="item[0] missing 'url'"),
    ]
    assert er.passed == 1
    assert er.failed == 1
    assert er.overall_verdict == RuleVerdict.FAIL
    report = er.to_report()
    assert "check1" in report
    assert "FAIL" in report
