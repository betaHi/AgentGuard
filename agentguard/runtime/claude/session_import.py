"""Import Claude SDK sessions into AgentGuard traces.

This module is intentionally defensive about SDK surface differences across
released versions. The current PyPI package exposes session helpers as
package-level functions, not as methods on ``ClaudeSDKClient``.
"""

from __future__ import annotations

from dataclasses import dataclass
import datetime as _dt
import inspect
import json
import os
import re
from pathlib import Path
import unicodedata
from typing import Any

from agentguard.core.trace import ExecutionTrace, Span, SpanStatus, SpanType


# Vendor list prices ($ per 1M tokens). Matched by substring against the
# ``model`` field in the raw Claude JSONL. First match wins; more specific
# entries must precede less specific ones.
#
# ``_BUILTIN_PRICING_DATE`` is the ISO date the built-in table was last
# reviewed against vendor list prices. Bump it whenever the rates below
# change. The viewer surfaces it so users can judge staleness at a glance.
_BUILTIN_PRICING_DATE = "2025-01-15"
_BUILTIN_PRICING: list[tuple[str, dict[str, float]]] = [
    # Anthropic Claude family
    ("opus",   {"input": 15.0, "output": 75.0, "cache_read": 1.50, "cache_creation": 18.75}),
    ("sonnet", {"input": 3.0,  "output": 15.0, "cache_read": 0.30, "cache_creation": 3.75}),
    ("haiku",  {"input": 0.80, "output": 4.0,  "cache_read": 0.08, "cache_creation": 1.0}),
    # OpenAI GPT-5 family (public list prices, flat cache_read = 50% of input).
    ("gpt-5-mini", {"input": 0.25, "output": 2.0,  "cache_read": 0.125, "cache_creation": 0.25}),
    ("gpt-5-nano", {"input": 0.05, "output": 0.40, "cache_read": 0.025, "cache_creation": 0.05}),
    ("gpt-5",      {"input": 1.25, "output": 10.0, "cache_read": 0.625, "cache_creation": 1.25}),
]

# Fallback rates for unrecognized model ids. We still charge the call —
# otherwise a brand-new model id silently zero-costs the trace. Sonnet rates
# are a deliberate midrange so neither over- nor under-estimates dominate.
_UNKNOWN_MODEL_RATES: dict[str, float] = {
    "input": 3.0, "output": 15.0, "cache_read": 0.30, "cache_creation": 3.75,
}

_REQUIRED_RATE_KEYS = ("input", "output", "cache_read", "cache_creation")


def _load_pricing_overrides() -> list[tuple[str, dict[str, float]]]:
    """Load user-supplied pricing from ``AGENTGUARD_PRICING_FILE`` or default paths.

    The file must be JSON mapping ``{"model-substring": {"input": ..., "output": ...,
    "cache_read": ..., "cache_creation": ...}}``. Entries from the override file
    are checked before the built-in table so users can correct any model id
    we don't ship with (e.g. ``gpt-5.4``, an internal gateway, a distilled
    model) without patching the importer.
    """
    candidates: list[Path] = []
    env_path = os.environ.get("AGENTGUARD_PRICING_FILE")
    if env_path:
        candidates.append(Path(env_path))
    candidates.append(Path.home() / ".agentguard" / "pricing.json")
    candidates.append(Path.cwd() / ".agentguard" / "pricing.json")

    for path in candidates:
        try:
            if not path.is_file():
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        result: list[tuple[str, dict[str, float]]] = []
        for key, rates in data.items():
            if not isinstance(key, str) or not isinstance(rates, dict):
                continue
            try:
                result.append((
                    key.lower(),
                    {name: float(rates[name]) for name in _REQUIRED_RATE_KEYS},
                ))
            except (KeyError, TypeError, ValueError):
                # Skip malformed entries but keep the rest.
                continue
        if result:
            return result
    return []


def _model_pricing_table() -> list[tuple[str, dict[str, float]]]:
    """Return the active pricing table (user overrides + built-in defaults)."""
    return _load_pricing_overrides() + _BUILTIN_PRICING


def _pricing_for(model: str | None) -> tuple[dict[str, float], bool]:
    """Return ``(rates, is_known)`` for a model id.

    ``is_known=False`` means we fell back to unknown-model rates and the
    caller may want to flag the span so downstream consumers can tell.
    """
    if isinstance(model, str):
        m = model.lower()
        for key, table in _model_pricing_table():
            if key in m:
                return table, True
    return _UNKNOWN_MODEL_RATES, False


def _estimate_cost_usd(
    *,
    model: str | None,
    input_tokens: int,
    output_tokens: int,
    cache_read: int,
    cache_creation: int,
) -> tuple[float | None, bool]:
    """Estimate per-call USD cost, returning ``(cost_usd, used_fallback)``.

    Returns ``(None, False)`` when there were no tokens to price.
    """
    if not any((input_tokens, output_tokens, cache_read, cache_creation)):
        return None, False
    rates, is_known = _pricing_for(model)
    cost = (
        input_tokens / 1_000_000 * rates["input"]
        + output_tokens / 1_000_000 * rates["output"]
        + cache_read / 1_000_000 * rates["cache_read"]
        + cache_creation / 1_000_000 * rates["cache_creation"]
    )
    return cost, not is_known


class ClaudeSessionImportError(RuntimeError):
    """Raised when Claude session import cannot be completed."""


@dataclass
class ClaudeSessionSummary:
    """Stable summary of a Claude session available for import."""

    session_id: str
    summary: str
    cwd: str = ""
    git_branch: str | None = None
    custom_title: str | None = None
    first_prompt: str | None = None
    last_modified: int | None = None
    file_size: int | None = None
    tag: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a CLI- and JSON-friendly dictionary."""
        return {
            "session_id": self.session_id,
            "summary": self.summary,
            "cwd": self.cwd,
            "git_branch": self.git_branch,
            "custom_title": self.custom_title,
            "first_prompt": self.first_prompt,
            "last_modified": self.last_modified,
            "file_size": self.file_size,
            "tag": self.tag,
        }


def list_claude_sessions(
    *,
    directory: str | None = None,
    limit: int | None = None,
    offset: int = 0,
    include_worktrees: bool = True,
) -> list[ClaudeSessionSummary]:
    """List Claude sessions that can be imported into AgentGuard traces."""
    sdk = _load_sdk_module()
    list_sessions = getattr(sdk, "list_sessions", None)
    if list_sessions is None:
        raise ClaudeSessionImportError(
            "Installed claude-agent-sdk does not expose list_sessions()"
        )
    sessions = _coerce_list(
        _call_sdk_helper(
            list_sessions,
            "list_sessions",
            directory=directory,
            limit=limit,
            offset=offset,
            include_worktrees=include_worktrees,
        ),
        "list_sessions",
    )
    summaries = [
        ClaudeSessionSummary(
            session_id=str(_maybe_attr(session, "session_id") or ""),
            summary=str(_maybe_attr(session, "summary") or "(untitled Claude session)"),
            cwd=str(_maybe_attr(session, "cwd") or ""),
            git_branch=_string_or_none(_maybe_attr(session, "git_branch")),
            custom_title=_string_or_none(_maybe_attr(session, "custom_title")),
            first_prompt=_string_or_none(_maybe_attr(session, "first_prompt")),
            last_modified=_int_or_none(_maybe_attr(session, "last_modified")),
            file_size=_int_or_none(_maybe_attr(session, "file_size")),
            tag=_string_or_none(_maybe_attr(session, "tag")),
        )
        for session in sessions
        if _maybe_attr(session, "session_id")
    ]
    summaries.sort(key=lambda item: item.last_modified or 0, reverse=True)
    return summaries


def import_claude_session(
    session_id: str,
    *,
    directory: str | None = None,
    include_subagents: bool = True,
) -> ExecutionTrace:
    """Import a Claude SDK session into an AgentGuard trace."""
    sdk = _load_sdk_module()
    session_info = _maybe_get_session_info(sdk, session_id, directory)
    session_messages = _load_session_messages(sdk, session_id, directory)
    if not session_messages:
        raise ClaudeSessionImportError(_session_not_found_message(session_id, directory))

    # The SDK strips timestamps from SessionMessage objects, so read them
    # directly from the raw ~/.claude/projects/<slug>/<session_id>.jsonl
    # file. Without this, every imported span has duration_ms=0 and the
    # diagnose report cannot surface real wait times.
    jsonl = _load_raw_jsonl_for_session(session_id, directory)

    trace = ExecutionTrace(
        trace_id=session_id,
        task=_trace_task(session_id, session_info),
        trigger="claude_session_import",
        status=SpanStatus.COMPLETED,
        metadata=_trace_metadata(session_info, directory),
    )
    trace.metadata["claude.session_id"] = session_id
    if jsonl.uuid_to_timestamp:
        trace.metadata["claude.timestamps_available"] = True

    root_span = _new_span(
        name=_root_span_name(session_info),
        span_type=SpanType.AGENT,
        trace_id=session_id,
        metadata={"runtime": "claude_sdk", "import.source": "session_messages"},
        input_data=_first_user_payload(session_messages),
        output_data=_last_assistant_payload(session_messages),
    )
    _apply_trace_bounds(root_span, jsonl)
    _annotate_completion_signal(root_span, trace, jsonl)
    trace.add_span(root_span)

    for span in _assistant_spans(
        messages=session_messages,
        trace_id=session_id,
        parent_span_id=root_span.span_id,
        metadata={"claude.scope": "session", "claude.session_id": session_id},
        jsonl=jsonl,
    ):
        trace.add_span(span)

    for span in _tool_wait_spans(
        jsonl=jsonl,
        trace_id=session_id,
        parent_span_id=root_span.span_id,
    ):
        trace.add_span(span)

    if include_subagents:
        _add_subagent_spans(trace, sdk, session_id, directory, root_span.span_id)

    trace.complete()
    # trace.complete() stamps the trace with *now* as ended_at, which is
    # misleading for imports that happened hours or days after the
    # session ran. Pin the trace window to what we observed in the JSONL.
    if jsonl.first_timestamp:
        trace.started_at = jsonl.first_timestamp
        trace.ended_at = jsonl.last_timestamp or jsonl.first_timestamp
    return trace


def _load_sdk_module() -> Any:
    """Import the Claude SDK package lazily.

    Also asserts that the installed version falls in the range we have
    verified against. The importer relies on ``get_session_messages`` and
    the JSONL layout, both of which have been known to shift between minor
    SDK releases — failing loudly here is far better than silently
    producing wrong numbers.
    """
    try:
        import claude_agent_sdk as sdk
    except ImportError as exc:
        raise ClaudeSessionImportError(
            "Claude session import requires 'claude-agent-sdk'. "
            "Install with: pip install 'agentguard[claude]'"
        ) from exc
    _assert_sdk_version_supported(sdk)
    return sdk


# Narrow range we have verified. Must stay in sync with pyproject.toml's
# ``claude`` extra. When bumping this, update tests/test_claude_sdk_contract.py
# so new SDK shape regressions are caught.
_SDK_MIN_VERSION: tuple[int, int, int] = (0, 5, 0)
_SDK_MAX_EXCLUSIVE: tuple[int, int, int] = (0, 8, 0)


def _assert_sdk_version_supported(sdk: Any) -> None:
    """Raise ``ClaudeSessionImportError`` if the installed SDK is out of range.

    Unknown / unparseable versions are allowed through with a best-effort
    check to avoid blocking development builds; mismatched known versions
    fail loudly with an actionable upgrade command.
    """
    raw = getattr(sdk, "__version__", None)
    if not isinstance(raw, str) or not raw:
        return
    parsed = _parse_sdk_version(raw)
    if parsed is None:
        return
    if parsed < _SDK_MIN_VERSION or parsed >= _SDK_MAX_EXCLUSIVE:
        min_s = ".".join(str(p) for p in _SDK_MIN_VERSION)
        max_s = ".".join(str(p) for p in _SDK_MAX_EXCLUSIVE)
        raise ClaudeSessionImportError(
            f"claude-agent-sdk {raw} is outside the verified range "
            f"[{min_s}, {max_s}). Install a supported version with: "
            f"pip install 'claude-agent-sdk>={min_s},<{max_s}'"
        )


def _parse_sdk_version(raw: str) -> tuple[int, int, int] | None:
    """Parse ``MAJOR.MINOR.PATCH`` prefixes into a comparable tuple."""
    head = raw.split("+", 1)[0].split("-", 1)[0]
    parts = head.split(".")
    if len(parts) < 2:
        return None
    try:
        major = int(parts[0])
        minor = int(parts[1])
        patch = int(parts[2]) if len(parts) >= 3 else 0
    except ValueError:
        return None
    return (major, minor, patch)


def _load_session_messages(sdk: Any, session_id: str, directory: str | None) -> list[Any]:
    """Load main-session transcript messages using the installed SDK surface."""
    get_session_messages = getattr(sdk, "get_session_messages", None)
    if get_session_messages is None:
        raise ClaudeSessionImportError(
            "Installed claude-agent-sdk does not expose get_session_messages()"
        )
    messages = _call_sdk_helper(
        get_session_messages,
        "get_session_messages",
        session_id,
        directory=directory,
    )
    return _coerce_list(messages, "get_session_messages")


def _maybe_get_session_info(sdk: Any, session_id: str, directory: str | None) -> Any | None:
    """Load optional Claude session metadata when the helper exists."""
    get_session_info = getattr(sdk, "get_session_info", None)
    if get_session_info is None:
        return None
    try:
        return _call_sdk_helper(
            get_session_info,
            "get_session_info",
            session_id,
            directory=directory,
        )
    except ClaudeSessionImportError:
        return None


def _helper_accepts_directory(helper: Any) -> bool:
    """Detect whether an SDK helper accepts a directory keyword."""
    try:
        signature = inspect.signature(helper)
    except (TypeError, ValueError):
        return True
    if "directory" in signature.parameters:
        return True
    return any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )


def _call_sdk_helper(
    helper: Any,
    helper_name: str,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Call a Claude SDK helper across minor signature differences."""
    if not callable(helper):
        raise ClaudeSessionImportError(f"Claude SDK helper {helper_name}() is unavailable")
    try:
        supported_kwargs = {
            key: value
            for key, value in kwargs.items()
            if value is not None and _helper_accepts_keyword(helper, key)
        }
        return helper(*args, **supported_kwargs)
    except ClaudeSessionImportError:
        raise
    except Exception as exc:
        directory = kwargs.get("directory")
        location = f" for directory '{directory}'" if directory else ""
        raise ClaudeSessionImportError(
            f"Claude SDK {helper_name}() failed{location}: {exc}"
        ) from exc

def _helper_accepts_keyword(helper: Any, keyword: str) -> bool:
    """Detect whether an SDK helper accepts a given keyword."""
    try:
        signature = inspect.signature(helper)
    except (TypeError, ValueError):
        return True
    if keyword in signature.parameters:
        return True
    return any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )


def _coerce_list(value: Any, helper_name: str) -> list[Any]:
    """Normalize Claude SDK helper outputs to lists."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, (str, bytes, dict)):
        raise ClaudeSessionImportError(
            f"Claude SDK {helper_name}() returned a non-list result"
        )
    try:
        return list(value)
    except TypeError as exc:
        raise ClaudeSessionImportError(
            f"Claude SDK {helper_name}() returned a non-list result"
        ) from exc


def _trace_task(session_id: str, session_info: Any | None) -> str:
    """Derive a task label for the imported trace."""
    summary = _maybe_attr(session_info, "summary")
    first_prompt = _maybe_attr(session_info, "first_prompt")
    if isinstance(summary, str) and summary.strip():
        return summary
    if isinstance(first_prompt, str) and first_prompt.strip():
        return first_prompt[:120]
    return f"Claude session {session_id}"
def _string_or_none(value: Any) -> str | None:
    """Normalize optional string-like metadata fields."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None

def _int_or_none(value: Any) -> int | None:
    """Normalize optional integer-like metadata fields."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _root_span_name(session_info: Any | None) -> str:
    """Derive a readable root span name."""
    title = _maybe_attr(session_info, "custom_title")
    if isinstance(title, str) and title.strip():
        return title
    return "claude-session"


def _trace_metadata(session_info: Any | None, directory: str | None) -> dict[str, Any]:
    """Serialize useful session metadata into the trace."""
    metadata: dict[str, Any] = {"runtime": "claude_sdk"}
    if directory:
        metadata["claude.directory"] = directory
    for key in (
        "summary",
        "custom_title",
        "first_prompt",
        "git_branch",
        "cwd",
        "tag",
        "created_at",
        "last_modified",
    ):
        value = _maybe_attr(session_info, key)
        if value is not None:
            metadata[f"claude.{key}"] = value
    return metadata


def _maybe_attr(value: Any, name: str) -> Any:
    """Read either object attributes or dictionary fields."""
    if value is None:
        return None
    if isinstance(value, dict):
        return value.get(name)
    return getattr(value, name, None)


def _message_type(message: Any) -> str:
    """Resolve a Claude session message type."""
    return str(_maybe_attr(message, "type") or "unknown")


def _message_uuid(message: Any) -> str:
    """Resolve a stable message identifier when present."""
    message_uuid = _maybe_attr(message, "uuid")
    return str(message_uuid) if message_uuid else ""


def _message_payload(message: Any) -> Any:
    """Resolve the message payload body."""
    return _maybe_attr(message, "message")


def _message_parent_tool_use_id(message: Any) -> str:
    """Resolve parent tool use id when present."""
    parent_tool_use_id = _maybe_attr(message, "parent_tool_use_id")
    return str(parent_tool_use_id) if parent_tool_use_id else ""


def _payload_text(payload: Any) -> str:
    """Extract a readable text summary from a Claude payload."""
    chunks = _collect_text_chunks(payload)
    text = " ".join(chunk.strip() for chunk in chunks if chunk and chunk.strip())
    return text[:500]


def _collect_text_chunks(value: Any) -> list[str]:
    """Recursively collect text-like chunks from nested payloads."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        chunks: list[str] = []
        for key in ("text", "content", "message", "name"):
            if key in value:
                chunks.extend(_collect_text_chunks(value[key]))
        return chunks
    if isinstance(value, (list, tuple)):
        chunks: list[str] = []
        for item in value:
            chunks.extend(_collect_text_chunks(item))
        return chunks
    if hasattr(value, "text"):
        return _collect_text_chunks(getattr(value, "text"))
    if hasattr(value, "content"):
        return _collect_text_chunks(getattr(value, "content"))
    return []


def _new_span(
    *,
    name: str,
    span_type: SpanType,
    trace_id: str,
    parent_span_id: str | None = None,
    input_data: Any | None = None,
    output_data: Any | None = None,
    metadata: dict[str, Any] | None = None,
    started_at: str | None = None,
    ended_at: str | None = None,
) -> Span:
    """Create a completed span, optionally pinned to explicit timestamps."""
    span = Span(
        trace_id=trace_id,
        parent_span_id=parent_span_id,
        span_type=span_type,
        name=name,
        status=SpanStatus.COMPLETED,
        input_data=input_data,
        output_data=output_data,
        metadata=metadata or {},
    )
    if started_at:
        span.started_at = started_at
        span.ended_at = ended_at or started_at
    else:
        span.ended_at = span.started_at
    return span


def _first_user_payload(messages: list[Any]) -> Any | None:
    """Capture the first user prompt for root span input."""
    for message in messages:
        if _message_type(message) == "user":
            return _message_payload(message)
    return None


def _last_assistant_payload(messages: list[Any]) -> Any | None:
    """Capture the last assistant reply for root span output."""
    for message in reversed(messages):
        if _message_type(message) == "assistant":
            return _message_payload(message)
    return None


def _assistant_spans(
    *,
    messages: list[Any],
    trace_id: str,
    parent_span_id: str,
    metadata: dict[str, Any],
    jsonl: "_JsonlIndex | None" = None,
) -> list[Span]:
    """Convert assistant messages into LLM spans."""
    spans: list[Span] = []
    for index, message in enumerate(messages, start=1):
        if _message_type(message) != "assistant":
            continue
        payload = _message_payload(message)
        span_metadata = dict(metadata)
        msg_uuid = _message_uuid(message)
        span_metadata["claude.message_uuid"] = msg_uuid
        parent_tool_use_id = _message_parent_tool_use_id(message)
        if parent_tool_use_id:
            span_metadata["claude.parent_tool_use_id"] = parent_tool_use_id
        ts = jsonl.uuid_to_timestamp.get(msg_uuid) if (jsonl and msg_uuid) else None
        usage = jsonl.uuid_to_usage.get(msg_uuid) if (jsonl and msg_uuid) else None
        token_count: int | None = None
        estimated_cost: float | None = None
        if usage:
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            cache_read = usage.get("cache_read_input_tokens", 0)
            cache_creation = usage.get("cache_creation_input_tokens", 0)
            total = input_tokens + output_tokens + cache_read + cache_creation
            if total > 0:
                token_count = total
            span_metadata["claude.usage.input_tokens"] = input_tokens
            span_metadata["claude.usage.output_tokens"] = output_tokens
            if cache_read:
                span_metadata["claude.usage.cache_read_input_tokens"] = cache_read
            if cache_creation:
                span_metadata["claude.usage.cache_creation_input_tokens"] = cache_creation
            model = usage.get("model")
            if model:
                span_metadata["claude.model"] = model
            estimated_cost, used_fallback_price = _estimate_cost_usd(
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_read=cache_read,
                cache_creation=cache_creation,
            )
            if estimated_cost is not None:
                span_metadata["claude.estimated_cost_usd"] = round(estimated_cost, 6)
                if used_fallback_price:
                    span_metadata["claude.cost_pricing"] = "fallback"
        span = _new_span(
            name=f"assistant-message-{index}",
            span_type=SpanType.LLM_CALL,
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            input_data={"summary": _payload_text(payload)},
            output_data=payload,
            metadata=span_metadata,
            started_at=ts,
            ended_at=ts,
        )
        if token_count is not None:
            span.token_count = token_count
        if estimated_cost is not None:
            span.estimated_cost_usd = estimated_cost
        spans.append(span)
    # The Claude SDK silently drops many assistant records the raw JSONL
    # retains (thinking blocks, tool-result carriers, compaction stubs...).
    # Re-emit those so token totals and cost-yield match ground truth.
    spans.extend(
        _reconcile_missing_usage_spans(
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            metadata=metadata,
            jsonl=jsonl,
            already_seen={
                m
                for m in (
                    _message_uuid(msg)
                    for msg in messages
                    if _message_type(msg) == "assistant"
                )
                if m
            },
            index_offset=sum(1 for m in messages if _message_type(m) == "assistant"),
        )
    )
    return spans


def _reconcile_missing_usage_spans(
    *,
    trace_id: str,
    parent_span_id: str,
    metadata: dict[str, Any],
    jsonl: "_JsonlIndex | None",
    already_seen: set[str],
    index_offset: int,
) -> list[Span]:
    """Emit LLM spans for usage-bearing JSONL entries the SDK omitted."""
    if not jsonl or not jsonl.uuid_to_usage:
        return []
    extras: list[Span] = []
    counter = index_offset
    for uuid, usage in jsonl.uuid_to_usage.items():
        if uuid in already_seen:
            continue
        input_tokens = int(usage.get("input_tokens") or 0)
        output_tokens = int(usage.get("output_tokens") or 0)
        cache_read = int(usage.get("cache_read_input_tokens") or 0)
        cache_creation = int(usage.get("cache_creation_input_tokens") or 0)
        if not any((input_tokens, output_tokens, cache_read, cache_creation)):
            continue
        counter += 1
        span_metadata = dict(metadata)
        span_metadata["claude.message_uuid"] = uuid
        span_metadata["claude.source"] = "jsonl_reconcile"
        span_metadata["claude.usage.input_tokens"] = input_tokens
        span_metadata["claude.usage.output_tokens"] = output_tokens
        if cache_read:
            span_metadata["claude.usage.cache_read_input_tokens"] = cache_read
        if cache_creation:
            span_metadata["claude.usage.cache_creation_input_tokens"] = cache_creation
        model = usage.get("model")
        if isinstance(model, str) and model:
            span_metadata["claude.model"] = model
        estimated_cost, used_fallback = _estimate_cost_usd(
            model=model if isinstance(model, str) else None,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read=cache_read,
            cache_creation=cache_creation,
        )
        if estimated_cost is not None:
            span_metadata["claude.estimated_cost_usd"] = round(estimated_cost, 6)
            if used_fallback:
                span_metadata["claude.cost_pricing"] = "fallback"
        ts = jsonl.uuid_to_timestamp.get(uuid)
        span = _new_span(
            name=f"assistant-message-{counter}",
            span_type=SpanType.LLM_CALL,
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            metadata=span_metadata,
            started_at=ts,
            ended_at=ts,
        )
        total = input_tokens + output_tokens + cache_read + cache_creation
        if total > 0:
            span.token_count = total
        if estimated_cost is not None:
            span.estimated_cost_usd = estimated_cost
        extras.append(span)
    return extras


def _add_subagent_spans(
    trace: ExecutionTrace,
    sdk: Any,
    session_id: str,
    directory: str | None,
    root_span_id: str,
) -> None:
    """Attach subagent spans when the installed SDK exposes the helpers."""
    list_subagents = getattr(sdk, "list_subagents", None)
    get_subagent_messages = getattr(sdk, "get_subagent_messages", None)
    if list_subagents is None or get_subagent_messages is None:
        trace.metadata["claude.subagents_unavailable"] = True
        return

    try:
        subagent_ids = _coerce_list(
            _call_sdk_helper(
                list_subagents,
                "list_subagents",
                session_id,
                directory=directory,
            ),
            "list_subagents",
        )
    except ClaudeSessionImportError as exc:
        trace.metadata["claude.subagents_unavailable"] = True
        trace.metadata["claude.subagents_error"] = str(exc)
        return

    trace.metadata["claude.subagent_count"] = len(subagent_ids)
    imported_count = 0
    skipped: list[dict[str, str]] = []
    for agent_id in subagent_ids:
        agent_name = str(agent_id)
        try:
            agent_messages = _coerce_list(
                _call_sdk_helper(
                    get_subagent_messages,
                    "get_subagent_messages",
                    session_id,
                    agent_id,
                    directory=directory,
                ),
                "get_subagent_messages",
            )
        except ClaudeSessionImportError as exc:
            skipped.append({"agent_id": agent_name, "reason": str(exc)})
            continue
        if not agent_messages:
            skipped.append({"agent_id": agent_name, "reason": "No Claude subagent messages found"})
            continue

        handoff_span = _new_span(
            name=f"claude-session → {agent_name}",
            span_type=SpanType.HANDOFF,
            trace_id=session_id,
            parent_span_id=root_span_id,
            metadata={"runtime": "claude_sdk", "claude.scope": "subagent_handoff"},
        )
        handoff_span.handoff_from = "claude-session"
        handoff_span.handoff_to = agent_name
        handoff_span.context_size_bytes = len(str(_first_user_payload(agent_messages) or ""))
        trace.add_span(handoff_span)

        agent_span = _new_span(
            name=agent_name,
            span_type=SpanType.AGENT,
            trace_id=session_id,
            parent_span_id=root_span_id,
            input_data=_first_user_payload(agent_messages),
            output_data=_last_assistant_payload(agent_messages),
            metadata={"runtime": "claude_sdk", "claude.scope": "subagent", "claude.agent_id": agent_name},
        )
        trace.add_span(agent_span)
        imported_count += 1
        subagent_jsonl = _load_raw_jsonl_for_subagent(session_id, agent_name)
        for span in _assistant_spans(
            messages=agent_messages,
            trace_id=session_id,
            parent_span_id=agent_span.span_id,
            metadata={"runtime": "claude_sdk", "claude.scope": "subagent", "claude.agent_id": agent_name},
            jsonl=subagent_jsonl,
        ):
            trace.add_span(span)
        # Subagent transcripts carry their own tool_use/tool_result pairs.
        # Without emitting tool_wait spans here the bottleneck/critical-path
        # analyses only see main-session tool waits (typically <50% of the
        # total) and misattribute the true slow tools.
        for span in _tool_wait_spans(
            jsonl=subagent_jsonl,
            trace_id=session_id,
            parent_span_id=agent_span.span_id,
        ):
            trace.add_span(span)
    trace.metadata["claude.subagent_imported_count"] = imported_count
    if skipped:
        trace.metadata["claude.subagent_import_skipped"] = skipped


# ---------------------------------------------------------------------------
# Raw JSONL timestamp enrichment
# ---------------------------------------------------------------------------


@dataclass
class _JsonlIndex:
    """Timestamp + tool-correlation index reconstructed from raw JSONL.

    ``uuid_to_usage`` holds the assistant ``usage`` block (input/output/cache
    tokens + model) keyed by message uuid. The Claude SDK drops it, but the
    raw JSONL keeps it — without this, every LLM span has ``token_count=0``
    and the cost panel shows ``$0``.
    """

    uuid_to_timestamp: dict[str, str]
    tool_use_by_id: dict[str, dict[str, Any]]
    tool_result_by_id: dict[str, dict[str, Any]]
    first_timestamp: str | None
    last_timestamp: str | None
    uuid_to_usage: dict[str, dict[str, Any]]
    last_stop_reason: str | None = None


_EMPTY_JSONL_INDEX = _JsonlIndex(
    uuid_to_timestamp={},
    tool_use_by_id={},
    tool_result_by_id={},
    first_timestamp=None,
    last_timestamp=None,
    uuid_to_usage={},
    last_stop_reason=None,
)


def _claude_projects_dir() -> Path:
    """Return the ~/.claude/projects root, respecting CLAUDE_CONFIG_DIR."""
    override = os.environ.get("CLAUDE_CONFIG_DIR")
    if override:
        base = Path(unicodedata.normalize("NFC", override))
    else:
        base = Path(unicodedata.normalize("NFC", str(Path.home() / ".claude")))
    return base / "projects"


def _session_not_found_message(session_id: str, directory: str | None) -> str:
    """Build an actionable error listing every path we actually checked.

    Users consistently hit this error when Claude stores sessions in a
    non-default directory (WSL, containerised dev, shared workstations).
    Listing the real search paths turns a mystery into a one-line fix.
    """
    projects_dir = _claude_projects_dir()
    lines = [
        f"No Claude session messages found for session '{session_id}'.",
        "Checked:",
        f"  - SDK default lookup (directory={directory!r})",
        f"  - {projects_dir}/*/{session_id}.jsonl",
    ]
    env_override = os.environ.get("CLAUDE_CONFIG_DIR")
    if env_override:
        lines.append(f"  - CLAUDE_CONFIG_DIR={env_override}")
    lines.extend([
        "",
        "Fixes to try:",
        "  1. agentguard list-claude-sessions --all --group-by-project",
        "  2. Pass --directory <project-dir> that was the cwd when Claude ran",
        "  3. Set CLAUDE_CONFIG_DIR=<path> if sessions live outside ~/.claude",
    ])
    return "\n".join(lines)


def _load_raw_jsonl_for_session(session_id: str, directory: str | None) -> _JsonlIndex:
    """Locate ``~/.claude/projects/*/<session_id>.jsonl`` and parse it.

    The Claude SDK strips timestamps when it decodes messages, so this
    reader is the only way to recover when each tool_use was issued and
    when its matching tool_result came back. Returns an empty index if
    the JSONL cannot be read; import must continue to work in that case.
    """
    projects_dir = _claude_projects_dir()
    if not projects_dir.is_dir():
        return _EMPTY_JSONL_INDEX

    target_name = f"{session_id}.jsonl"
    candidate: Path | None = None
    try:
        for project_dir in projects_dir.iterdir():
            if not project_dir.is_dir():
                continue
            candidate_path = project_dir / target_name
            if candidate_path.is_file():
                candidate = candidate_path
                break
    except OSError:
        return _EMPTY_JSONL_INDEX

    if candidate is None:
        return _EMPTY_JSONL_INDEX

    return _parse_session_jsonl(candidate)


def _load_raw_jsonl_for_subagent(session_id: str, agent_id: str) -> _JsonlIndex:
    """Parse ``<session>/subagents/agent-<id>.jsonl`` when present.

    Subagent transcripts live in a sibling folder to the main session JSONL.
    Without parsing them, every subagent LLM span is imported without usage
    or model metadata and the cost-yield analysis silently under-counts.
    """
    projects_dir = _claude_projects_dir()
    if not projects_dir.is_dir():
        return _EMPTY_JSONL_INDEX
    target = f"agent-{agent_id}.jsonl"
    try:
        for project_dir in projects_dir.iterdir():
            if not project_dir.is_dir():
                continue
            candidate = project_dir / session_id / "subagents" / target
            if candidate.is_file():
                return _parse_session_jsonl(candidate)
    except OSError:
        return _EMPTY_JSONL_INDEX
    return _EMPTY_JSONL_INDEX


def _parse_session_jsonl(path: Path) -> _JsonlIndex:
    """Parse a Claude session JSONL file into a timestamp/tool index.

    Reads line-by-line rather than loading the full file into memory,
    which matters for long-running sessions (multi-MB JSONL). A malformed
    line is skipped so a single bad record never drops the whole import.
    """
    uuid_to_timestamp: dict[str, str] = {}
    tool_use_by_id: dict[str, dict[str, Any]] = {}
    tool_result_by_id: dict[str, dict[str, Any]] = {}
    uuid_to_usage: dict[str, dict[str, Any]] = {}
    first_ts: str | None = None
    last_ts: str | None = None
    last_stop_reason: str | None = None

    try:
        fp = path.open("r", encoding="utf-8", errors="replace")
    except OSError:
        return _EMPTY_JSONL_INDEX

    with fp:
        for raw_line in fp:
            line = raw_line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(record, dict):
                continue

            ts = record.get("timestamp")
            uuid = record.get("uuid")
            if isinstance(ts, str) and ts and isinstance(uuid, str) and uuid:
                uuid_to_timestamp[uuid] = ts
                if first_ts is None:
                    first_ts = ts
                last_ts = ts

            message = record.get("message") or {}
            content = message.get("content") if isinstance(message, dict) else None

            # Capture per-message token usage so LLM spans can report real counts.
            if isinstance(message, dict) and isinstance(uuid, str) and uuid:
                usage = message.get("usage")
                if isinstance(usage, dict):
                    model = message.get("model")
                    record_usage: dict[str, Any] = {
                        "input_tokens": _as_int(usage.get("input_tokens")),
                        "output_tokens": _as_int(usage.get("output_tokens")),
                        "cache_creation_input_tokens": _as_int(
                            usage.get("cache_creation_input_tokens")
                        ),
                        "cache_read_input_tokens": _as_int(
                            usage.get("cache_read_input_tokens")
                        ),
                    }
                    if isinstance(model, str) and model:
                        record_usage["model"] = model
                    uuid_to_usage[uuid] = record_usage
                # Track the most recent assistant stop_reason — this is the raw
                # Q4 completion signal (end_turn vs. max_tokens vs. error).
                stop_reason = message.get("stop_reason")
                if isinstance(stop_reason, str) and stop_reason:
                    last_stop_reason = stop_reason

            if not isinstance(content, list):
                continue

            for block in content:
                if not isinstance(block, dict):
                    continue
                block_type = block.get("type")
                if block_type == "tool_use":
                    block_id = block.get("id")
                    if isinstance(block_id, str) and block_id and isinstance(ts, str):
                        tool_input = block.get("input")
                        tool_use_by_id[block_id] = {
                            "timestamp": ts,
                            "name": str(block.get("name") or ""),
                            "command": _extract_tool_input_summary(tool_input),
                            "raw_input": tool_input if isinstance(tool_input, dict) else {},
                            "message_uuid": uuid or "",
                        }
                elif block_type == "tool_result":
                    block_id = block.get("tool_use_id")
                    if isinstance(block_id, str) and block_id and isinstance(ts, str):
                        tool_result_by_id[block_id] = {
                            "timestamp": ts,
                            "message_uuid": uuid or "",
                        }

    return _JsonlIndex(
        uuid_to_timestamp=uuid_to_timestamp,
        tool_use_by_id=tool_use_by_id,
        tool_result_by_id=tool_result_by_id,
        first_timestamp=first_ts,
        last_timestamp=last_ts,
        uuid_to_usage=uuid_to_usage,
        last_stop_reason=last_stop_reason,
    )


def _apply_trace_bounds(root_span: Span, jsonl: _JsonlIndex) -> None:
    """Pin the root span to the first/last observed JSONL timestamps."""
    if not jsonl.first_timestamp:
        return
    root_span.started_at = jsonl.first_timestamp
    root_span.ended_at = jsonl.last_timestamp or jsonl.first_timestamp


# Map the assistant stop_reason to a 0–1 Q4 completion signal.
# end_turn is a clean end; tool_use / stop_sequence also indicate the
# model chose to stop on purpose. max_tokens means the reply was truncated
# by the provider, which is the single most common "paid for nothing"
# failure mode and must drag yield down. Error / refusal bottom the scale.
_STOP_REASON_SIGNAL: dict[str, float] = {
    "end_turn": 1.0,
    "stop_sequence": 0.9,
    "tool_use": 0.85,
    "pause_turn": 0.6,
    "max_tokens": 0.35,
    "refusal": 0.2,
    "error": 0.15,
}


def _annotate_completion_signal(
    root_span: Span, trace: ExecutionTrace, jsonl: _JsonlIndex
) -> None:
    """Expose Q4 completion signals derived from the final assistant turn.

    Two signals are produced:

    1. ``claude.stop_reason`` — raw stop reason from the last assistant
       message (``end_turn`` / ``max_tokens`` / ``error`` / …).
    2. ``claude.deliverables`` — count of concrete artifact references
       extracted from the final assistant payload (file paths, code
       fences, URLs). A session that ended cleanly *and* produced
       artifacts scores higher than one that ended cleanly with no
       tangible output.

    The numeric ``claude.completion_signal`` / ``claude.quality`` values
    blend both inputs so the analyser's cost-yield calculation can no
    longer treat a "nice reply with nothing shipped" as success.
    """
    reason = jsonl.last_stop_reason
    if reason:
        root_span.metadata["claude.stop_reason"] = reason
        trace.metadata["claude.stop_reason"] = reason

    deliverables = _extract_deliverable_refs(root_span.output_data)
    if deliverables:
        sample = sorted(deliverables)[:5]
        root_span.metadata["claude.deliverables"] = sample
        trace.metadata["claude.deliverables"] = sample
        trace.metadata["claude.deliverables_count"] = len(deliverables)

    if not reason:
        return
    base = _STOP_REASON_SIGNAL.get(reason)
    if base is None:
        return
    # No deliverables → treat a "clean" stop as only partially successful.
    # With ≥ 1 deliverable, scale up modestly; saturate at 1.0.
    if deliverables:
        signal = min(1.0, base + 0.05 * min(len(deliverables), 3))
    else:
        signal = base * 0.7
    # Metadata key split on "." → "quality" is recognised by the analyzer
    # as an explicit numeric quality signal with weight 1.0.
    root_span.metadata["claude.quality"] = signal
    trace.metadata["claude.completion_signal"] = signal


# Regexes compiled once — the final assistant payload is scanned to
# detect concrete artifact references, which is the strongest passive
# signal that the agent actually produced something.
_DELIVERABLE_CODE_FENCE = re.compile(r"```[\w+-]*\n", re.MULTILINE)
_DELIVERABLE_FILE_PATH = re.compile(
    r"(?:^|[\s(\[`'\"])"  # preceded by boundary
    r"((?:\.{1,2}/|/)?[\w.-]+/[\w./-]+\.[A-Za-z0-9]{1,6})"  # a/b.ext or ./a.md
    r"(?=$|[\s)\]`'\",:;])",  # followed by boundary
    re.MULTILINE,
)
_DELIVERABLE_URL = re.compile(r"https?://[\w./\-%?#=&+]+")


def _extract_deliverable_refs(payload: Any) -> set[str]:
    """Return a set of artifact references found in ``payload``.

    Looks for file paths, fenced code blocks, and URLs. Kept
    intentionally conservative: short identifiers that happen to look
    like paths are rejected because they dominate false positives in
    real assistant chatter.
    """
    text = _flatten_payload_to_text(payload)
    if not text:
        return set()
    refs: set[str] = set()
    for match in _DELIVERABLE_FILE_PATH.finditer(text):
        path = match.group(1)
        if len(path) >= 4:
            refs.add(path)
    for match in _DELIVERABLE_URL.finditer(text):
        refs.add(match.group(0))
    fence_count = len(_DELIVERABLE_CODE_FENCE.findall(text))
    for i in range(min(fence_count, 3)):
        refs.add(f"<code-block-{i + 1}>")
    return refs


def _flatten_payload_to_text(payload: Any) -> str:
    """Flatten a Claude assistant payload (usually a list of blocks) to text."""
    if payload is None:
        return ""
    if isinstance(payload, str):
        return payload
    if isinstance(payload, list):
        parts = []
        for block in payload:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    value = block.get("text")
                    if isinstance(value, str):
                        parts.append(value)
                elif block.get("type") == "tool_use":
                    # tool_use inputs commonly include file paths.
                    tool_input = block.get("input")
                    if isinstance(tool_input, dict):
                        parts.append(json.dumps(tool_input, default=str))
        return "\n".join(parts)
    if isinstance(payload, dict):
        return json.dumps(payload, default=str)
    return str(payload)


def _tool_wait_spans(
    *,
    jsonl: _JsonlIndex,
    trace_id: str,
    parent_span_id: str,
) -> list[Span]:
    """Emit explicit tool spans covering tool_use → tool_result waits.

    Each pair becomes a single TOOL span whose duration is the real wall
    clock time the tool took to return. This is what lets the diagnose
    report surface things like "Bash wait = 82.7s" — otherwise all spans
    have duration_ms=0 and the bottleneck is invisible.
    """
    spans: list[Span] = []
    for tool_use_id, use in jsonl.tool_use_by_id.items():
        result = jsonl.tool_result_by_id.get(tool_use_id)
        if not result:
            continue
        start = use.get("timestamp")
        end = result.get("timestamp")
        if not isinstance(start, str) or not isinstance(end, str):
            continue
        delta_ms = _timestamp_delta_ms(start, end)
        name_label = use.get("name") or "tool"
        summary = use.get("command") or ""
        metadata = {
            "claude.scope": "tool_wait",
            "claude.tool_name": name_label,
            "claude.tool_use_id": tool_use_id,
            "claude.tool_use_message_uuid": use.get("message_uuid") or "",
            "claude.tool_result_message_uuid": result.get("message_uuid") or "",
        }
        if summary:
            metadata["claude.tool_summary"] = summary
        raw_input = use.get("raw_input") or {}
        if isinstance(raw_input, dict):
            for k in ("subagent_type", "description", "file_path", "pattern"):
                v = raw_input.get(k)
                if isinstance(v, str) and v:
                    metadata[f"claude.tool_input.{k}"] = v[:200]
        spans.append(
            _new_span(
                name=f"tool:{name_label}",
                span_type=SpanType.TOOL,
                trace_id=trace_id,
                parent_span_id=parent_span_id,
                input_data={"command": summary},
                output_data={"wait_ms": delta_ms},
                metadata=metadata,
                started_at=start,
                ended_at=end,
            )
        )
    return spans


def _timestamp_delta_ms(start: str, end: str) -> float:
    """Return the difference in milliseconds between two ISO timestamps."""
    try:
        start_dt = _dt.datetime.fromisoformat(start.replace("Z", "+00:00"))
        end_dt = _dt.datetime.fromisoformat(end.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    return max(0.0, (end_dt - start_dt).total_seconds() * 1000.0)


def _as_int(value: Any) -> int:
    """Coerce a JSONL usage field into a non-negative int (0 on failure)."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return 0
    return n if n >= 0 else 0


# Keys to probe, in order of descriptive quality, when building a
# one-line summary of a tool_use input block. Different tools use
# different names: Bash has `command`, Task has `description`+`prompt`,
# Read/Write have `file_path`, Grep has `pattern`, etc.
_TOOL_INPUT_SUMMARY_KEYS = (
    "command",
    "description",
    "prompt",
    "file_path",
    "path",
    "pattern",
    "query",
    "url",
    "question",
    "expression",
)


def _extract_tool_input_summary(tool_input: Any, max_len: int = 200) -> str:
    """Return a short human-readable summary of a tool_use input block.

    ``command`` alone only covers Bash; Claude's Task tool carries the
    real intent in ``description``/``prompt``, Read/Write use
    ``file_path``, Grep uses ``pattern``. Returning "" here means the
    HTML cards cannot distinguish one tool call from another with the
    same name, which is exactly how ``tool:Agent`` ends up duplicated
    in the hotspot list.
    """
    if not isinstance(tool_input, dict):
        return ""
    for key in _TOOL_INPUT_SUMMARY_KEYS:
        v = tool_input.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()[:max_len]
    return ""
