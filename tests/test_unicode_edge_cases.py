"""Test: Unicode agent names, emoji in metadata, very long strings.

Production traces may contain CJK names, emoji, RTL text, or very
long strings. Nothing should crash, corrupt, or silently drop data.
"""

import json

from agentguard.analysis import (
    analyze_bottleneck,
    analyze_context_flow,
    analyze_cost_yield,
    analyze_decisions,
    analyze_failures,
    analyze_flow,
)
from agentguard.builder import TraceBuilder
from agentguard.cli.main import _build_analysis_dict
from agentguard.scoring import score_trace
from agentguard.summarize import summarize_trace
from agentguard.tree import tree_to_text
from agentguard.web.viewer import trace_to_html_string


def _unicode_trace():
    """Trace with CJK names, emoji metadata, and long strings."""
    return (TraceBuilder("用户画像分析 🎯")
        .agent("协调者", duration_ms=5000,
               input_data={"任务": "分析用户偏好", "emoji": "🚀🔥💡"})
            .agent("研究員", duration_ms=2000,
                   input_data={"query": "café résumé naïve"},
                   output_data={"結果": "成功 ✅"})
                .tool("搜索工具 🔍", duration_ms=500)
            .end()
            .agent("كاتب", duration_ms=1500,  # Arabic
                   input_data={"text": "مرحبا بالعالم"},
                   output_data={"report": "تقرير"})
            .end()
        .end()
        .build())


def _long_string_trace():
    """Trace with very long agent name and metadata values."""
    long_name = "agent_" + "x" * 500
    long_value = "v" * 50000
    return (TraceBuilder("long strings test")
        .agent(long_name, duration_ms=1000,
               input_data={"key": long_value},
               output_data={"result": long_value})
        .end()
        .build())


class TestUnicodeAnalysis:
    def test_all_analysis_no_crash(self):
        t = _unicode_trace()
        analyze_failures(t)
        analyze_flow(t)
        analyze_bottleneck(t)
        analyze_context_flow(t)
        analyze_cost_yield(t)
        analyze_decisions(t)

    def test_score(self):
        s = score_trace(_unicode_trace())
        assert 0 <= s.overall <= 100

    def test_html_preserves_unicode(self):
        html = trace_to_html_string(_unicode_trace())
        assert "协调者" in html
        assert "研究員" in html
        assert "🔍" in html

    def test_cli_json_unicode(self):
        d = _build_analysis_dict(_unicode_trace())
        assert d["trace"]["task"] == "用户画像分析 🎯"

    def test_tree_unicode(self):
        txt = tree_to_text(_unicode_trace())
        assert "协调者" in txt

    def test_json_round_trip(self):
        t = _unicode_trace()
        j = t.to_json()
        parsed = json.loads(j)
        assert parsed["task"] == "用户画像分析 🎯"
        names = [s["name"] for s in parsed["spans"]]
        assert "研究員" in names
        assert "كاتب" in names

    def test_summarize(self):
        assert summarize_trace(_unicode_trace()) is not None


class TestLongStrings:
    def test_analysis_no_crash(self):
        t = _long_string_trace()
        analyze_failures(t)
        analyze_bottleneck(t)
        score_trace(t)

    def test_html_no_crash(self):
        html = trace_to_html_string(_long_string_trace())
        assert len(html) > 100

    def test_json_round_trip(self):
        t = _long_string_trace()
        j = t.to_json()
        parsed = json.loads(j)
        assert len(parsed["spans"][0]["name"]) > 500

    def test_truncate_long_data(self):
        t = _long_string_trace()
        j = t.to_json(truncate=True)
        assert json.loads(j) is not None


class TestSpecialCharacters:
    def test_null_bytes_in_data(self):
        t = (TraceBuilder("null test")
            .agent("agent", duration_ms=100,
                   input_data={"val": "hello\x00world"})
            .end().build())
        j = t.to_json()
        assert json.loads(j) is not None

    def test_newlines_in_error(self):
        t = (TraceBuilder("newline test")
            .agent("agent", duration_ms=100,
                   status="failed",
                   error="line1\nline2\nline3")
            .end().build())
        html = trace_to_html_string(t)
        assert "line1" in html

    def test_html_entities_escaped(self):
        t = (TraceBuilder("<script>alert('xss')</script>")
            .agent("agent<br>", duration_ms=100,
                   input_data={"key": '<img onerror="alert(1)">'})
            .end().build())
        html = trace_to_html_string(t)
        # Task name should be escaped, not rendered as raw HTML
        assert "&lt;script&gt;" in html
        assert "agent&lt;br&gt;" in html
