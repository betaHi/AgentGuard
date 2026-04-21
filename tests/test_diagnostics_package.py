"""Tests for the v2 diagnostics compatibility package."""

from agentguard import analysis as legacy_analysis
from agentguard import context_flow as legacy_context_flow
from agentguard import correlation as legacy_correlation
from agentguard import flowgraph as legacy_flowgraph
from agentguard import propagation as legacy_propagation
from agentguard import scoring as legacy_scoring
from agentguard import timeline as legacy_timeline
from agentguard import tree as legacy_tree
from agentguard.diagnostics import (
    analyze_bottleneck,
    analyze_context_flow_deep,
    analyze_correlations,
    analyze_propagation,
    build_flow_graph,
    build_timeline,
    compute_tree_stats,
    score_trace,
)
from agentguard.diagnostics.analysis import analyze_failures
from agentguard.diagnostics.context_flow import ContextFlowAnalysis
from agentguard.diagnostics.correlation import CorrelationReport
from agentguard.diagnostics.flowgraph import FlowGraph
from agentguard.diagnostics.propagation import PropagationAnalysis
from agentguard.diagnostics.scoring import TraceScore
from agentguard.diagnostics.timeline import Timeline
from agentguard.diagnostics.tree import TreeStats


def test_diagnostics_root_exports_match_legacy_functions() -> None:
    assert analyze_bottleneck is legacy_analysis.analyze_bottleneck
    assert analyze_context_flow_deep is legacy_context_flow.analyze_context_flow_deep
    assert analyze_correlations is legacy_correlation.analyze_correlations
    assert analyze_propagation is legacy_propagation.analyze_propagation
    assert build_flow_graph is legacy_flowgraph.build_flow_graph
    assert build_timeline is legacy_timeline.build_timeline
    assert compute_tree_stats is legacy_tree.compute_tree_stats
    assert score_trace is legacy_scoring.score_trace


def test_diagnostics_submodules_export_expected_public_types() -> None:
    assert analyze_failures is legacy_analysis.analyze_failures
    assert ContextFlowAnalysis is legacy_context_flow.ContextFlowAnalysis
    assert CorrelationReport is legacy_correlation.CorrelationReport
    assert FlowGraph is legacy_flowgraph.FlowGraph
    assert PropagationAnalysis is legacy_propagation.PropagationAnalysis
    assert TraceScore is legacy_scoring.TraceScore
    assert Timeline is legacy_timeline.Timeline
    assert TreeStats is legacy_tree.TreeStats