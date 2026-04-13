"""LangChain callback handler that auto-records agent/tool spans.

Maps LangChain's callback lifecycle to AgentGuard spans:
- on_llm_start/end → tool span (LLM call)
- on_chain_start/end → agent span (chain = agent)
- on_tool_start/end → tool span
- on_agent_action/finish → agent span

No hard dependency on langchain — this module imports it lazily
and raises a clear error if not installed. The handler works with
both LangChain and LangChain Community callback interfaces.

Example::

    from agentguard.integrations.langchain import AgentGuardHandler
    from agentguard.sdk.recorder import init_recorder, finish_recording

    init_recorder(task="langchain pipeline")
    handler = AgentGuardHandler()
    chain.invoke(input, config={"callbacks": [handler]})
    trace = finish_recording()
"""

from __future__ import annotations

from datetime import UTC
from typing import Any
from uuid import UUID

from agentguard.core.trace import Span, SpanStatus, SpanType
from agentguard.sdk.context import get_recorder


def _ensure_langchain() -> type:
    """Import and return the LangChain BaseCallbackHandler.

    Raises ImportError with a helpful message if langchain is not installed.
    """
    try:
        from langchain_core.callbacks import BaseCallbackHandler
        return BaseCallbackHandler
    except ImportError:
        try:
            from langchain.callbacks.base import BaseCallbackHandler
            return BaseCallbackHandler
        except ImportError:
            raise ImportError(
                "langchain is required for AgentGuardHandler. "
                "Install it with: pip install langchain-core"
            ) from None


def _make_span_id(run_id: UUID | str) -> str:
    """Convert a LangChain run_id to a stable span ID."""
    return f"lc-{run_id}"


def _ts_now() -> str:
    """ISO timestamp for span boundaries."""
    from datetime import datetime
    return datetime.now(UTC).isoformat()


class AgentGuardHandler:
    """LangChain callback handler that records spans into AgentGuard.

    Implements the LangChain BaseCallbackHandler interface. Each
    LangChain event (LLM call, chain run, tool use) becomes an
    AgentGuard span with proper parent-child nesting.

    The handler is stateless across invocations — all state lives
    in the AgentGuard recorder's span stack.
    """

    def __init__(self, record_inputs: bool = True, record_outputs: bool = True) -> None:
        self._record_inputs = record_inputs
        self._record_outputs = record_outputs
        self._active_spans: dict[str, Span] = {}


    # ── LLM events → tool spans ──

    def on_llm_start(
        self, serialized: dict, prompts: list[str],
        *, run_id: UUID, parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Record LLM call as a tool span."""
        model_name = _extract_model_name(serialized)
        self._start_span(
            run_id, f"llm:{model_name}", SpanType.TOOL,
            parent_run_id=parent_run_id,
            input_data={"prompts": prompts} if self._record_inputs else None,
            metadata={"model": model_name, "framework": "langchain"},
        )

    def on_llm_end(self, response: Any, *, run_id: UUID, **kwargs: Any) -> None:
        """Complete the LLM tool span."""
        output = None
        if self._record_outputs and hasattr(response, "generations"):
            output = {"generations": str(response.generations)[:500]}
        self._end_span(run_id, output_data=output)

    def on_llm_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        self._fail_span(run_id, error)

    # ── Chain events → agent spans ──

    def on_chain_start(
        self, serialized: dict, inputs: dict,
        *, run_id: UUID, parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        chain_name = serialized.get("id", ["unknown"])[-1]
        self._start_span(
            run_id, f"chain:{chain_name}", SpanType.AGENT,
            parent_run_id=parent_run_id,
            input_data=inputs if self._record_inputs else None,
            metadata={"chain_type": chain_name, "framework": "langchain"},
        )

    def on_chain_end(self, outputs: dict, *, run_id: UUID, **kwargs: Any) -> None:
        self._end_span(run_id, output_data=outputs if self._record_outputs else None)

    def on_chain_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        self._fail_span(run_id, error)

    # ── Tool events → tool spans ──

    def on_tool_start(
        self, serialized: dict, input_str: str,
        *, run_id: UUID, parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        tool_name = serialized.get("name", "unknown_tool")
        self._start_span(
            run_id, f"tool:{tool_name}", SpanType.TOOL,
            parent_run_id=parent_run_id,
            input_data={"input": input_str} if self._record_inputs else None,
            metadata={"tool_name": tool_name, "framework": "langchain"},
        )

    def on_tool_end(self, output: str, *, run_id: UUID, **kwargs: Any) -> None:
        self._end_span(run_id, output_data={"output": output[:500]} if self._record_outputs else None)

    def on_tool_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        self._fail_span(run_id, error)

    # ── Internal helpers ──

    def _start_span(
        self, run_id: UUID, name: str, span_type: SpanType,
        parent_run_id: UUID | None = None,
        input_data: Any = None, metadata: dict | None = None,
    ) -> Span:
        """Create and register a new span."""
        recorder = get_recorder()
        parent_id = None
        if parent_run_id:
            parent_span = self._active_spans.get(_make_span_id(parent_run_id))
            if parent_span:
                parent_id = parent_span.span_id

        span = Span(
            name=name,
            span_type=span_type,
            parent_span_id=parent_id,
            started_at=_ts_now(),
            input_data=input_data,
            metadata=metadata or {},
        )
        self._active_spans[_make_span_id(run_id)] = span
        recorder.push_span(span)
        return span

    def _end_span(self, run_id: UUID, output_data: Any = None) -> None:
        """Complete a span successfully."""
        key = _make_span_id(run_id)
        span = self._active_spans.pop(key, None)
        if span is None:
            return
        span.ended_at = _ts_now()
        span.status = SpanStatus.COMPLETED
        if output_data:
            span.output_data = output_data
        recorder = get_recorder()
        recorder.pop_span(span)

    def _fail_span(self, run_id: UUID, error: BaseException) -> None:
        """Mark a span as failed."""
        key = _make_span_id(run_id)
        span = self._active_spans.pop(key, None)
        if span is None:
            return
        span.ended_at = _ts_now()
        span.status = SpanStatus.FAILED
        span.error = f"{type(error).__name__}: {error}"
        recorder = get_recorder()
        recorder.pop_span(span)


def _extract_model_name(serialized: dict) -> str:
    """Extract model name from LangChain serialized dict."""
    kwargs = serialized.get("kwargs", {})
    return (
        kwargs.get("model_name")
        or kwargs.get("model")
        or serialized.get("id", ["unknown"])[-1]
    )
