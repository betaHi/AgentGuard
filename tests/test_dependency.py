"""Tests for agent dependency graph."""

import pytest
from agentguard.core.trace import ExecutionTrace, Span, SpanType, SpanStatus
from agentguard.builder import TraceBuilder
from agentguard.dependency import build_dependency_graph


class TestDependencyGraph:
    def test_handoff_dependency(self):
        trace = (TraceBuilder("handoff_test")
            .agent("researcher", duration_ms=3000).end()
            .handoff("researcher", "writer", context_size=1000)
            .agent("writer", duration_ms=2000).end()
            .build())
        
        graph = build_dependency_graph(trace)
        handoff_deps = [d for d in graph.dependencies if d.dep_type == "handoff"]
        assert len(handoff_deps) == 1
        assert handoff_deps[0].from_agent == "researcher"
        assert handoff_deps[0].to_agent == "writer"

    def test_data_dependency(self):
        trace = (TraceBuilder("data_test")
            .agent("a", output_data={"articles": [1, 2]}).end()
            .agent("b", input_data={"articles": [1, 2]}).end()
            .build())
        
        graph = build_dependency_graph(trace)
        data_deps = [d for d in graph.dependencies if d.dep_type == "data"]
        assert len(data_deps) >= 1

    def test_root_and_leaf(self):
        trace = (TraceBuilder("chain")
            .agent("a").end()
            .handoff("a", "b")
            .agent("b").end()
            .handoff("b", "c")
            .agent("c").end()
            .build())
        
        graph = build_dependency_graph(trace)
        assert "a" in graph.root_agents
        assert "c" in graph.leaf_agents

    def test_mermaid(self):
        trace = (TraceBuilder("mermaid")
            .agent("a").end()
            .handoff("a", "b")
            .agent("b").end()
            .build())
        
        graph = build_dependency_graph(trace)
        mermaid = graph.to_mermaid()
        assert "graph LR" in mermaid

    def test_report(self):
        trace = (TraceBuilder("report")
            .agent("a").end()
            .agent("b").end()
            .build())
        graph = build_dependency_graph(trace)
        report = graph.to_report()
        assert "Dependency" in report

    def test_empty(self):
        trace = ExecutionTrace(task="empty")
        graph = build_dependency_graph(trace)
        assert graph.agents == []
        assert graph.dependencies == []

    def test_to_dict(self):
        trace = (TraceBuilder("dict")
            .agent("a").end()
            .build())
        graph = build_dependency_graph(trace)
        d = graph.to_dict()
        assert "agents" in d
        assert "dependencies" in d
