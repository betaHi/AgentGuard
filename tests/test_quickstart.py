"""Tests that verify the quickstart guide code actually works."""



class TestQuickstartCode:
    """Run the code from docs/quickstart.md to verify it works."""

    def test_basic_instrumentation(self):
        """Quickstart Step 1: Record a trace."""
        from agentguard import mark_context_used, record_agent, record_handoff
        from agentguard.sdk.recorder import finish_recording, init_recorder

        init_recorder(task="My Pipeline")

        @record_agent(name="researcher")
        def research(topic):
            return {"articles": ["a1", "a2"], "raw": "...", "meta": {}}

        @record_agent(name="writer")
        def write(articles):
            return {"draft": "# My Blog Post"}

        data = research("AI agents")
        h = record_handoff("researcher", "writer", context=data, summary="2 articles")
        mark_context_used(h, used_keys=["articles"])
        write(data["articles"])

        trace = finish_recording()
        assert len(trace.spans) >= 3  # 2 agents + 1 handoff

    def test_analysis(self):
        """Quickstart Step 2: Analyze."""
        from agentguard.builder import TraceBuilder
        from agentguard.context_flow import analyze_context_flow_deep
        from agentguard.flowgraph import build_flow_graph
        from agentguard.metrics import extract_metrics
        from agentguard.propagation import analyze_propagation
        from agentguard.scoring import score_trace
        from agentguard.summarize import summarize_trace

        trace = (TraceBuilder("test_pipeline")
            .agent("researcher", duration_ms=3000, token_count=1000)
                .tool("web_search", duration_ms=1000)
            .end()
            .handoff("researcher", "writer", context_size=1000)
            .agent("writer", duration_ms=5000)
            .end()
            .build())

        score = score_trace(trace)
        assert 0 <= score.overall <= 100

        m = extract_metrics(trace)
        assert m.agent_count == 2

        prop = analyze_propagation(trace)
        assert prop.total_failures == 0

        graph = build_flow_graph(trace)
        mermaid = graph.to_mermaid()
        assert "graph" in mermaid

        flow = analyze_context_flow_deep(trace)
        assert isinstance(flow.compression_ratio, float)

        summary = summarize_trace(trace)
        assert len(summary) > 20

    def test_sla_check(self):
        """Quickstart Step 5: SLA Checking."""
        from agentguard.builder import TraceBuilder
        from agentguard.sla import SLAChecker

        trace = (TraceBuilder("sla_test")
            .agent("a", duration_ms=2000).end()
            .build())

        sla = (SLAChecker()
            .max_duration_ms(10000)
            .min_success_rate(0.95)
            .max_cost_usd(1.0)
            .min_score(70))

        result = sla.check(trace)
        assert isinstance(result.passed, bool)

    def test_alert_rules(self):
        """Quickstart Step 6: Alert Rules."""
        from agentguard.alerts import AlertEngine, rule_score_below, rule_trace_failed
        from agentguard.builder import TraceBuilder

        trace = (TraceBuilder("alert_test")
            .agent("a", status="failed", error="crash").end()
            .build())

        engine = AlertEngine()
        engine.add_rule(rule_trace_failed())
        engine.add_rule(rule_score_below(60, severity="critical"))

        alerts = engine.evaluate(trace)
        assert len(alerts) >= 1

    def test_trace_builder(self):
        """Quickstart Step 4: TraceBuilder."""
        from agentguard.builder import TraceBuilder

        trace = (TraceBuilder("Content Pipeline")
            .agent("researcher", duration_ms=5000, token_count=2000, cost_usd=0.06)
                .tool("web_search", duration_ms=2000)
                .llm_call("claude", duration_ms=3000, token_count=1500, cost_usd=0.04)
            .end()
            .handoff("researcher", "writer", context_size=2000)
            .agent("writer", duration_ms=8000)
            .end()
            .build())

        assert len(trace.spans) >= 5
