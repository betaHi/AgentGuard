"""Tests for trace templates."""

import pytest
from agentguard.templates import (
    research_pipeline, code_review_pipeline, support_pipeline,
    etl_pipeline, list_templates, create_from_template,
)
from agentguard.core.trace import SpanType


class TestTemplates:
    def test_research(self):
        trace = research_pipeline()
        assert len(trace.spans) >= 8
        agents = [s for s in trace.spans if s.span_type == SpanType.AGENT]
        assert len(agents) >= 3

    def test_research_with_failure(self):
        trace = research_pipeline(include_failures=True)
        failed = [s for s in trace.spans if s.status.value == "failed"]
        assert len(failed) >= 1

    def test_code_review(self):
        trace = code_review_pipeline()
        assert len(trace.spans) >= 8

    def test_support(self):
        trace = support_pipeline()
        assert len(trace.spans) >= 8

    def test_etl(self):
        trace = etl_pipeline()
        assert len(trace.spans) >= 8

    def test_list_templates(self):
        templates = list_templates()
        assert "research" in templates
        assert "code_review" in templates
        assert len(templates) >= 4

    def test_create_from_template(self):
        trace = create_from_template("research")
        assert trace.task.startswith("Research")

    def test_unknown_template(self):
        with pytest.raises(KeyError):
            create_from_template("nonexistent")

    def test_all_templates_valid(self):
        """Every template should produce a valid trace."""
        from agentguard.schema import validate_trace_dict
        for name in list_templates():
            trace = create_from_template(name)
            errors = validate_trace_dict(trace.to_dict())
            assert errors == [], f"Template '{name}' produced invalid trace: {errors}"
