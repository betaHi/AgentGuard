"""AgentGuard — Record, Replay, Evaluate, and Guard your AI Agents.

Integration styles:

    # Style 1: Decorators (sync)
    @record_agent(name="my-agent", version="v1")
    def my_agent(task): ...

    # Style 2: Decorators (async)
    @record_agent_async(name="my-agent", version="v1")
    async def my_agent(task): ...

    # Style 3: Context managers (sync)
    with AgentTrace(name="my-agent", version="v1") as agent:
        ...

    # Style 4: Context managers (async)
    async with AsyncAgentTrace(name="my-agent", version="v1") as agent:
        ...

    # Style 6: Explicit handoff recording
    from agentguard import record_handoff
    record_handoff(from_agent="a", to_agent="b", context={...})

    # Style 7: Spawned processes
    from agentguard.sdk.distributed import inject_trace_context, init_recorder_from_env
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
from agentguard.sdk.threading import TraceThread
from agentguard.settings import configure, get_settings, reset_settings
from agentguard.sla import SLAChecker
from agentguard.summarize import summarize_brief, summarize_trace
from agentguard.templates import create_from_template
from agentguard.timeline import build_timeline
from agentguard.tree import compute_tree_stats, tree_to_text

__all__ = [
    "record_agent", "record_tool",
    "record_agent_async", "record_tool_async",
    "AgentTrace", "ToolContext",
    "AsyncAgentTrace", "AsyncToolContext",
    "TraceThread",
    "record_handoff", "mark_context_used", "detect_context_loss", "record_decision",
    "analyze_propagation", "hypothetical_failure",
    "build_flow_graph",
    "analyze_context_flow_deep",
    "analyze_correlations", "fingerprint_span",
    "analyze_handoff_chains", "compute_context_integrity",
    "diff_flow_graphs", "diff_context_flow",
    "score_trace", "aggregate_traces",
    "auto_annotate", "AnnotationStore",
    "filter_spans", "filter_traces", "sample_traces",
    "TraceBuilder", "build_timeline", "tree_to_text", "compute_tree_stats",
    "normalize_trace", "summarize_trace", "summarize_brief",
    "compare_traces", "build_agent_profiles", "build_dependency_graph",
    "SLAChecker", "AlertEngine", "rule_trace_failed", "rule_score_below",
    "extract_metrics", "batch_analyze",
    "generate_trace", "generate_batch", "create_from_template",
    "register_analyzer", "register_exporter", "get_plugin_registry",
    "configure", "get_settings", "reset_settings", "annotate", "set_correlation_id", "set_parent_trace",
]
