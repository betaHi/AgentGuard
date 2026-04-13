"""Tests for LangChain callback handler integration.

Uses mocks to avoid requiring langchain as a test dependency.
"""

import sys
import types
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

# Mock langchain_core before importing handler
_mock_lc = types.ModuleType("langchain_core")
_mock_cb = types.ModuleType("langchain_core.callbacks")


class _FakeBaseHandler:
    """Minimal mock of LangChain BaseCallbackHandler."""
    pass


_mock_cb.BaseCallbackHandler = _FakeBaseHandler
_mock_lc.callbacks = _mock_cb
sys.modules["langchain_core"] = _mock_lc
sys.modules["langchain_core.callbacks"] = _mock_cb

import contextlib

from agentguard.core.trace import SpanStatus, SpanType
from agentguard.integrations.langchain import (
    AgentGuardHandler,
    _extract_model_name,
    _make_span_id,
    _ts_now,
)
from agentguard.sdk.recorder import finish_recording, init_recorder


@pytest.fixture(autouse=True)
def _fresh_recorder():
    init_recorder(task="langchain test", trigger="test")
    yield
    with contextlib.suppress(Exception):
        finish_recording()


class TestAgentGuardHandler:
    def test_llm_start_end_creates_tool_span(self):
        handler = AgentGuardHandler()
        rid = uuid4()
        handler.on_llm_start(
            {"kwargs": {"model_name": "gpt-4"}, "id": ["openai"]},
            ["Hello"], run_id=rid,
        )
        handler.on_llm_end(
            MagicMock(generations=[["response"]]), run_id=rid,
        )
        trace = finish_recording()
        llm_spans = [s for s in trace.spans if "llm:" in s.name]
        assert len(llm_spans) == 1
        assert llm_spans[0].status == SpanStatus.COMPLETED

    def test_chain_start_end_creates_agent_span(self):
        handler = AgentGuardHandler()
        rid = uuid4()
        handler.on_chain_start(
            {"id": ["langchain", "RunnableSequence"]},
            {"input": "test"}, run_id=rid,
        )
        handler.on_chain_end({"output": "result"}, run_id=rid)
        trace = finish_recording()
        chain_spans = [s for s in trace.spans if "chain:" in s.name]
        assert len(chain_spans) == 1
        assert chain_spans[0].span_type == SpanType.AGENT

    def test_tool_start_end(self):
        handler = AgentGuardHandler()
        rid = uuid4()
        handler.on_tool_start(
            {"name": "calculator"}, "2+2", run_id=rid,
        )
        handler.on_tool_end("4", run_id=rid)
        trace = finish_recording()
        tool_spans = [s for s in trace.spans if "tool:" in s.name]
        assert len(tool_spans) == 1

    def test_llm_error_marks_failed(self):
        handler = AgentGuardHandler()
        rid = uuid4()
        handler.on_llm_start(
            {"kwargs": {}, "id": ["model"]}, ["x"], run_id=rid,
        )
        handler.on_llm_error(ConnectionError("timeout"), run_id=rid)
        trace = finish_recording()
        failed = [s for s in trace.spans if s.status == SpanStatus.FAILED]
        assert len(failed) == 1
        assert "ConnectionError" in failed[0].error

    def test_parent_child_nesting(self):
        handler = AgentGuardHandler()
        parent_id = uuid4()
        child_id = uuid4()
        handler.on_chain_start(
            {"id": ["Chain"]}, {}, run_id=parent_id,
        )
        handler.on_llm_start(
            {"kwargs": {"model": "gpt-4"}, "id": ["llm"]}, ["hi"],
            run_id=child_id, parent_run_id=parent_id,
        )
        handler.on_llm_end(MagicMock(generations=[]), run_id=child_id)
        handler.on_chain_end({}, run_id=parent_id)
        trace = finish_recording()
        llm_span = [s for s in trace.spans if "llm:" in s.name][0]
        chain_span = [s for s in trace.spans if "chain:" in s.name][0]
        assert llm_span.parent_span_id == chain_span.span_id

    def test_no_inputs_when_disabled(self):
        handler = AgentGuardHandler(record_inputs=False)
        rid = uuid4()
        handler.on_llm_start(
            {"kwargs": {}, "id": ["m"]}, ["secret"], run_id=rid,
        )
        handler.on_llm_end(MagicMock(generations=[]), run_id=rid)
        trace = finish_recording()
        span = [s for s in trace.spans if "llm:" in s.name][0]
        assert span.input_data is None

    def test_end_unknown_run_id_no_crash(self):
        handler = AgentGuardHandler()
        handler.on_llm_end(MagicMock(generations=[]), run_id=uuid4())
        # Should not raise


class TestHelpers:
    def test_make_span_id(self):
        uid = uuid4()
        assert _make_span_id(uid) == f"lc-{uid}"

    def test_extract_model_name(self):
        assert _extract_model_name({"kwargs": {"model_name": "gpt-4"}}) == "gpt-4"
        assert _extract_model_name({"kwargs": {"model": "claude"}}) == "claude"
        assert _extract_model_name({"id": ["openai", "ChatOpenAI"]}) == "ChatOpenAI"

    def test_ts_now_is_iso(self):
        ts = _ts_now()
        assert "T" in ts
        assert "+" in ts or "Z" in ts
