"""AgentGuard — diagnostics for multi-agent orchestration.

**Publishable API — start here.**

One question, one import::

    from agentguard import diagnose_claude_session

    report, html = diagnose_claude_session("<session-id>", html_out="report.html")

For the full programmatic surface::

    from agentguard.diagnostics import (
        import_claude_session,
        diagnose,
        render_html_report,
        analyze_context_flow,
        analyze_cost_yield,
        analyze_bottleneck,
        analyze_decisions,
        score_trace,
    )

Legacy capture styles (decorators, context managers, threading, distributed,
evolution, alerts, ...) remain importable from their original submodules for
backwards compatibility, but are **not** part of the recommended product
surface and are not re-exported here.
"""

try:
    from importlib.metadata import version as _get_version
    __version__: str = _get_version("agentguard")
except Exception:
    __version__ = "0.1.0"  # fallback for editable/uninstalled mode

from agentguard.aggregate import aggregate_traces
from agentguard.alerts import AlertEngine, rule_score_below, rule_trace_failed
from agentguard.annotations import AnnotationStore, auto_annotate
from agentguard.batch import batch_analyze
from agentguard.builder import TraceBuilder
from agentguard.comparison import compare_traces
from agentguard.context_flow import analyze_context_flow_deep
from agentguard.correlation import analyze_correlations, fingerprint_span
from agentguard.dependency import build_dependency_graph
from agentguard.diff import diff_context_flow, diff_flow_graphs
from agentguard.filter import filter_spans, filter_traces, sample_traces
from agentguard.flowgraph import build_flow_graph
from agentguard.generate import generate_batch, generate_trace
from agentguard.metrics import extract_metrics
from agentguard.normalize import normalize_trace
from agentguard.plugin import get_plugin_registry, register_analyzer, register_exporter
from agentguard.profile import build_agent_profiles
from agentguard.propagation import (
    analyze_handoff_chains,
    analyze_propagation,
    compute_context_integrity,
    hypothetical_failure,
)
from agentguard.scoring import score_trace
from agentguard.sdk.async_decorators import record_agent_async, record_tool_async
from agentguard.sdk.context import AgentTrace, AsyncAgentTrace, AsyncToolContext, ToolContext
from agentguard.sdk.decorators import record_agent, record_tool
from agentguard.sdk.handoff import detect_context_loss, mark_context_used, record_decision, record_handoff
from agentguard.sdk.recorder import annotate, set_correlation_id, set_parent_trace
from agentguard.sdk.threading import (
    TraceThread,
    disable_auto_trace_threading,
    enable_auto_trace_threading,
    is_auto_trace_threading_enabled,
)
from agentguard.settings import configure, get_settings, reset_settings
from agentguard.sla import SLAChecker
from agentguard.summarize import summarize_brief, summarize_trace
from agentguard.templates import create_from_template
from agentguard.timeline import build_timeline
from agentguard.tree import compute_tree_stats, tree_to_text

# ---------------------------------------------------------------------------
# Curated public surface (the only names documented for publishable use).
# Everything else imported above is kept for backwards compatibility only.
# ---------------------------------------------------------------------------
from agentguard.core.trace import ExecutionTrace, Span, SpanStatus, SpanType
from agentguard.diagnostics import (
    DiagnosticReport,
    analyze_bottleneck,
    analyze_context_flow,
    analyze_cost_yield,
    analyze_counterfactual,
    analyze_decisions,
    analyze_failures,
    diagnose,
    render_html_report,
)
from agentguard.runtime.claude import import_claude_session, list_claude_sessions


def diagnose_claude_session(
    session_id: str,
    *,
    directory: str | None = None,
    include_subagents: bool = True,
    html_out: str | None = None,
) -> tuple[DiagnosticReport, str | None]:
    """Import and diagnose a Claude session in a single call.

    This is the single recommended entry point for new users:

        >>> from agentguard import diagnose_claude_session
        >>> report, html_path = diagnose_claude_session(
        ...     "abc-123", html_out="report.html",
        ... )

    Parameters
    ----------
    session_id:
        The Claude session id (see :func:`list_claude_sessions`).
    directory:
        Optional Claude session working directory.
    include_subagents:
        When True (default), imports subagent transcripts too.
    html_out:
        If given, writes an interactive HTML report to this path and
        returns the path as the second element of the tuple.

    Returns
    -------
    (report, html_path)
        ``report`` is a :class:`~agentguard.diagnostics.DiagnosticReport`.
        ``html_path`` is the written HTML path (or ``None`` if
        ``html_out`` was not provided).
    """
    trace = import_claude_session(
        session_id,
        directory=directory,
        include_subagents=include_subagents,
    )
    report = diagnose(trace)
    html_path: str | None = None
    if html_out is not None:
        html_path = render_html_report(trace, output_path=html_out)
    return report, html_path


__all__ = [
    # One-call entry point
    "diagnose_claude_session",
    # Claude session access
    "import_claude_session", "list_claude_sessions",
    # Core data model
    "ExecutionTrace", "Span", "SpanStatus", "SpanType",
    # The 5-question diagnostics
    "diagnose", "DiagnosticReport",
    "analyze_bottleneck", "analyze_context_flow", "analyze_cost_yield",
    "analyze_counterfactual", "analyze_decisions", "analyze_failures",
    # Rendering
    "render_html_report",
    # Settings
    "configure", "get_settings", "reset_settings",
]
