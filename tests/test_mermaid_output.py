"""Test Mermaid diagram output from various modules."""

from agentguard.builder import TraceBuilder
from agentguard.dependency import build_dependency_graph
from agentguard.flowgraph import build_flow_graph


class TestMermaidOutput:
    def test_flowgraph_mermaid(self):
        trace = (TraceBuilder("mermaid_test")
            .agent("researcher", duration_ms=3000)
                .tool("web_search", duration_ms=1000)
            .end()
            .handoff("researcher", "writer", context_size=1000)
            .agent("writer", duration_ms=5000)
            .end()
            .build())

        graph = build_flow_graph(trace)
        mermaid = graph.to_mermaid()

        assert "graph TD" in mermaid
        assert "researcher" in mermaid
        assert "writer" in mermaid
        assert "-->" in mermaid

    def test_dependency_mermaid(self):
        trace = (TraceBuilder("dep_mermaid")
            .agent("a", output_data={"data": [1]}).end()
            .handoff("a", "b", context_size=500)
            .agent("b", input_data={"data": [1]}).end()
            .build())

        graph = build_dependency_graph(trace)
        mermaid = graph.to_mermaid()

        assert "graph LR" in mermaid

    def test_mermaid_escapes_special_chars(self):
        trace = (TraceBuilder("special chars")
            .agent("agent-with-dashes", duration_ms=1000).end()
            .agent("agent_with_underscores", duration_ms=1000).end()
            .build())

        graph = build_flow_graph(trace)
        mermaid = graph.to_mermaid()
        # Should not crash on special characters
        assert len(mermaid) > 0
