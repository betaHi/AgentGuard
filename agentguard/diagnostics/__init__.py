"""AgentGuard diagnostics — the curated, publishable public API.

This package is the recommended entry point for diagnosing a real
multi-agent session. Every top-level ``agentguard.*`` module remains
importable for backward compatibility, but new users should start here.

Typical workflow::

    from agentguard.diagnostics import (
        import_claude_session,
        list_claude_sessions,
        diagnose,
        render_html_report,
    )

    sessions = list_claude_sessions()
    trace = import_claude_session(sessions[0].session_id)
    report = diagnose(trace)
    html = render_html_report(trace)

The five diagnostic questions (see ``GUARDRAILS.md``) mapped to this API:

    Q1  Who did what, when?         — ``ExecutionTrace`` / ``Span``
    Q2  Did information propagate?  — ``analyze_context_flow``
    Q3  Where did time/money go?    — ``analyze_bottleneck``,
                                       ``analyze_cost_yield``
    Q4  Did the task complete?      — ``trace.metadata['claude.stop_reason']``
                                       plus ``score_trace``
    Q5  What would you change?      — ``analyze_decisions``,
                                       ``analyze_counterfactual``
"""

from dataclasses import dataclass
from typing import Any

from agentguard.analysis import (  # noqa: F401
    BottleneckReport,
    ContextFlowPoint,
    ContextFlowReport,
    CostYieldEntry,
    CostYieldPathSummary,
    CostYieldReport,
    CounterfactualAnalysis,
    CounterfactualResult,
    DecisionAnalysis,
    DecisionRecord,
    DurationAnomaly,
    DurationAnomalyReport,
    FailureAnalysis,
    FailureNode,
    FlowAnalysis,
    HandoffInfo,
    RepeatedBadDecision,
    WorkflowPattern,
    WorkflowPatternAnalysis,
    analyze_bottleneck,
    analyze_context_flow,
    analyze_cost,
    analyze_cost_yield,
    analyze_counterfactual,
    analyze_decisions,
    analyze_failures,
    analyze_flow,
    analyze_retries,
    analyze_timing,
    analyze_workflow_patterns,
    detect_duration_anomalies,
    detect_repeated_bad_decisions,
)
from agentguard.context_flow import (  # noqa: F401
    ContextBandwidth,
    ContextFlowAnalysis,
    ContextSnapshot,
    ContextTransition,
    analyze_context_flow_deep,
)
from agentguard.correlation import (  # noqa: F401
    CorrelatedEvent,
    CorrelationReport,
    SpanFingerprint,
    analyze_correlations,
    correlate_failures_to_handoffs,
    detect_patterns,
    fingerprint_span,
)
from agentguard.flowgraph import (  # noqa: F401
    ExecutionPhase,
    FlowGraph,
    FlowNode,
    build_flow_graph,
)
from agentguard.propagation import (  # noqa: F401
    CausalLink,
    CausalChain,
    PropagationAnalysis,
    analyze_handoff_chains,
    analyze_propagation,
    compute_context_integrity,
    hypothetical_failure,
)
from agentguard.scoring import ScoreComponent, TraceScore, score_trace  # noqa: F401
from agentguard.timeline import EventType, Timeline, TimelineEvent, build_timeline  # noqa: F401
from agentguard.tree import (  # noqa: F401
    TreeStats,
    compute_tree_stats,
    detect_cycles,
    find_orphans,
    find_roots,
    tree_to_text,
)

__all__ = [
    "BottleneckReport",
    "CausalChain",
    "CausalLink",
    "ContextBandwidth",
    "ContextFlowAnalysis",
    "ContextFlowPoint",
    "ContextFlowReport",
    "ContextSnapshot",
    "ContextTransition",
    "CorrelatedEvent",
    "CorrelationReport",
    "CostYieldEntry",
    "CostYieldPathSummary",
    "CostYieldReport",
    "CounterfactualAnalysis",
    "CounterfactualResult",
    "DecisionAnalysis",
    "DecisionRecord",
    "DurationAnomaly",
    "DurationAnomalyReport",
    "EventType",
    "ExecutionPhase",
    "FailureAnalysis",
    "FailureNode",
    "FlowAnalysis",
    "FlowGraph",
    "FlowNode",
    "HandoffInfo",
    "PropagationAnalysis",
    "RepeatedBadDecision",
    "ScoreComponent",
    "SpanFingerprint",
    "Timeline",
    "TimelineEvent",
    "TraceScore",
    "TreeStats",
    "WorkflowPattern",
    "WorkflowPatternAnalysis",
    "analyze_bottleneck",
    "analyze_context_flow",
    "analyze_context_flow_deep",
    "analyze_correlations",
    "analyze_cost",
    "analyze_cost_yield",
    "analyze_counterfactual",
    "analyze_decisions",
    "analyze_failures",
    "analyze_flow",
    "analyze_handoff_chains",
    "analyze_propagation",
    "analyze_retries",
    "analyze_timing",
    "analyze_workflow_patterns",
    "build_flow_graph",
    "build_timeline",
    "compute_context_integrity",
    "compute_tree_stats",
    "correlate_failures_to_handoffs",
    "detect_cycles",
    "detect_duration_anomalies",
    "detect_patterns",
    "detect_repeated_bad_decisions",
    "find_orphans",
    "find_roots",
    "fingerprint_span",
    "hypothetical_failure",
    "score_trace",
    "tree_to_text",
    # Curated top-level workflow API (see module docstring).
    "ExecutionTrace", "Span", "SpanStatus", "SpanType",
    "import_claude_session", "list_claude_sessions",
    "diagnose", "DiagnosticReport",
    "render_html_report",
]


# ---------------------------------------------------------------------------
# Curated top-level workflow API
# ---------------------------------------------------------------------------
from agentguard.core.trace import (  # noqa: E402
    ExecutionTrace, Span, SpanStatus, SpanType,
)
from agentguard.runtime.claude import (  # noqa: E402
    import_claude_session, list_claude_sessions,
)
from agentguard.web.viewer import (  # noqa: E402
    generate_report_from_trace,
    trace_to_html_string,
)


@dataclass
class DiagnosticReport:
    """Composite answer to the 5 diagnostic questions for a single trace."""

    trace: ExecutionTrace
    score: Any
    failures: Any
    bottleneck: Any
    context_flow: Any
    cost_yield: Any
    decisions: Any

    def to_dict(self) -> dict[str, Any]:
        """Dump as a plain dict suitable for JSON serialisation."""
        def _dump(obj: Any) -> Any:
            if obj is None:
                return None
            if hasattr(obj, "to_dict"):
                return obj.to_dict()
            if hasattr(obj, "__dict__"):
                return {
                    k: v for k, v in obj.__dict__.items()
                    if not k.startswith("_")
                }
            return obj
        return {
            "trace_id": self.trace.trace_id,
            "score": _dump(self.score),
            "failures": _dump(self.failures),
            "bottleneck": _dump(self.bottleneck),
            "context_flow": _dump(self.context_flow),
            "cost_yield": _dump(self.cost_yield),
            "decisions": _dump(self.decisions),
        }


def diagnose(trace: ExecutionTrace) -> DiagnosticReport:
    """Run the full 5-question diagnosis against a trace.

    This is the one-call entry point that bundles the individual analyzers
    (``analyze_failures``, ``analyze_bottleneck``, ``analyze_context_flow``,
    ``analyze_cost_yield``, ``analyze_decisions``) and ``score_trace`` into
    a single :class:`DiagnosticReport`.
    """
    return DiagnosticReport(
        trace=trace,
        score=score_trace(trace),
        failures=analyze_failures(trace),
        bottleneck=analyze_bottleneck(trace),
        context_flow=analyze_context_flow(trace),
        cost_yield=analyze_cost_yield(trace),
        decisions=analyze_decisions(trace),
    )


def render_html_report(
    trace: ExecutionTrace,
    *,
    output_path: str | None = None,
) -> str:
    """Render a single self-contained interactive HTML report.

    If ``output_path`` is given, the report is written there and the path
    is returned; otherwise the HTML string itself is returned.
    """
    if output_path is not None:
        return generate_report_from_trace(trace, output_path)
    return trace_to_html_string(trace)