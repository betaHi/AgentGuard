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
from pathlib import Path
import unicodedata
from typing import Any

from agentguard.core.trace import ExecutionTrace, Span, SpanStatus, SpanType


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
        raise ClaudeSessionImportError(f"No Claude session messages found for session '{session_id}'")

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
    """Import the Claude SDK package lazily."""
    try:
        import claude_agent_sdk as sdk
    except ImportError as exc:
        raise ClaudeSessionImportError(
            "Claude session import requires 'claude-agent-sdk' to be installed"
        ) from exc
    return sdk


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
        spans.append(span)
    return spans


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
        for span in _assistant_spans(
            messages=agent_messages,
            trace_id=session_id,
            parent_span_id=agent_span.span_id,
            metadata={"runtime": "claude_sdk", "claude.scope": "subagent", "claude.agent_id": agent_name},
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


_EMPTY_JSONL_INDEX = _JsonlIndex(
    uuid_to_timestamp={},
    tool_use_by_id={},
    tool_result_by_id={},
    first_timestamp=None,
    last_timestamp=None,
    uuid_to_usage={},
)


def _claude_projects_dir() -> Path:
    """Return the ~/.claude/projects root, respecting CLAUDE_CONFIG_DIR."""
    override = os.environ.get("CLAUDE_CONFIG_DIR")
    if override:
        base = Path(unicodedata.normalize("NFC", override))
    else:
        base = Path(unicodedata.normalize("NFC", str(Path.home() / ".claude")))
    return base / "projects"


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


def _parse_session_jsonl(path: Path) -> _JsonlIndex:
    """Parse a Claude session JSONL file into a timestamp/tool index."""
    uuid_to_timestamp: dict[str, str] = {}
    tool_use_by_id: dict[str, dict[str, Any]] = {}
    tool_result_by_id: dict[str, dict[str, Any]] = {}
    uuid_to_usage: dict[str, dict[str, Any]] = {}
    first_ts: str | None = None
    last_ts: str | None = None

    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return _EMPTY_JSONL_INDEX

    for line in raw.splitlines():
        line = line.strip()
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
    )


def _apply_trace_bounds(root_span: Span, jsonl: _JsonlIndex) -> None:
    """Pin the root span to the first/last observed JSONL timestamps."""
    if not jsonl.first_timestamp:
        return
    root_span.started_at = jsonl.first_timestamp
    root_span.ended_at = jsonl.last_timestamp or jsonl.first_timestamp


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
