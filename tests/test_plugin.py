"""Tests for plugin system."""

import pytest
from agentguard.core.trace import ExecutionTrace, Span, SpanStatus
from agentguard.plugin import PluginRegistry, get_plugin_registry


@pytest.fixture
def registry():
    return PluginRegistry()


@pytest.fixture
def trace():
    t = ExecutionTrace(task="plugin_test")
    t.add_span(Span(name="a", status=SpanStatus.COMPLETED))
    return t


class TestPluginRegistry:
    def test_register_analyzer(self, registry, trace):
        def my_analyzer(t):
            return {"span_count": len(t.spans)}
        
        registry.register_analyzer("my_analyzer", my_analyzer, author="test")
        result = registry.run_analyzer("my_analyzer", trace)
        assert result["span_count"] == 1

    def test_register_exporter(self, registry, trace):
        def my_exporter(t):
            return f"TRACE: {t.task}"
        
        registry.register_exporter("my_exporter", my_exporter)
        result = registry.run_exporter("my_exporter", trace)
        assert result == "TRACE: plugin_test"

    def test_run_all(self, registry, trace):
        registry.register_analyzer("a1", lambda t: {"count": len(t.spans)})
        registry.register_analyzer("a2", lambda t: {"task": t.task})
        
        results = registry.run_all_analyzers(trace)
        assert "a1" in results
        assert "a2" in results

    def test_list_plugins(self, registry):
        registry.register_analyzer("analyzer1", lambda t: {})
        registry.register_exporter("exporter1", lambda t: "")
        
        plugins = registry.list_plugins()
        assert len(plugins) == 2
        assert registry.plugin_count == 2

    def test_error_handling(self, registry, trace):
        def bad_analyzer(t):
            raise ValueError("boom")
        
        registry.register_analyzer("bad", bad_analyzer)
        results = registry.run_all_analyzers(trace)
        assert "error" in results["bad"]

    def test_missing_analyzer(self, registry, trace):
        with pytest.raises(KeyError):
            registry.run_analyzer("nonexistent", trace)

    def test_plugin_info(self, registry):
        registry.register_analyzer("test", lambda t: {}, version="1.0", author="dev", description="A test plugin")
        plugins = registry.list_plugins()
        assert plugins[0].name == "test"
        assert plugins[0].version == "1.0"
        assert plugins[0].author == "dev"
