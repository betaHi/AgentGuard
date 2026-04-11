"""Tests for self-reflection and evolution engine."""

import tempfile
from pathlib import Path
from agentguard.core.trace import ExecutionTrace, Span, SpanType
from agentguard.evolve import EvolutionEngine, Reflection


def _make_trace_with_failure():
    t = ExecutionTrace(task="test")
    coord = Span(name="coordinator", span_type=SpanType.AGENT)
    
    # Agent with handled failure (fallback)
    a = Span(name="resilient", span_type=SpanType.AGENT, parent_span_id=coord.span_id)
    tool = Span(name="api", span_type=SpanType.TOOL, parent_span_id=a.span_id)
    tool.fail("timeout")
    fallback = Span(name="cache", span_type=SpanType.TOOL, parent_span_id=a.span_id)
    fallback.complete()
    a.complete()  # agent succeeded despite tool failure
    
    # Agent with unhandled failure
    b = Span(name="fragile", span_type=SpanType.AGENT, parent_span_id=coord.span_id)
    b.fail("crash")
    
    coord.complete()
    for s in [coord, a, tool, fallback, b]:
        t.add_span(s)
    t.complete()
    return t


def test_reflect_extracts_lessons():
    """reflect() extracts lessons from a trace."""
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = EvolutionEngine(knowledge_dir=f"{tmpdir}/kb")
        trace = _make_trace_with_failure()
        
        reflection = engine.reflect(trace)
        assert len(reflection.lessons) >= 2  # at least: unhandled failure + handled failure
        
        # Should have a lesson about fragile agent
        fragile_lessons = [l for l in reflection.lessons if l.agent == "fragile"]
        assert len(fragile_lessons) >= 1
        assert "unhandled" in fragile_lessons[0].observation.lower()


def test_learn_accumulates_knowledge():
    """learn() persists lessons and reinforces on repetition."""
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = EvolutionEngine(knowledge_dir=f"{tmpdir}/kb")
        trace = _make_trace_with_failure()
        
        # First run
        engine.learn(trace)
        assert engine.kb.trace_count == 1
        initial_lessons = len(engine.kb.lessons)
        
        # Second run — same failures should reinforce confidence
        engine.learn(trace)
        assert engine.kb.trace_count == 2
        
        # Confidence should have increased for repeated lessons
        for l in engine.kb.lessons.values():
            if l.occurrences > 1:
                assert l.confidence > 0.5  # reinforced


def test_knowledge_persists_to_disk():
    """Knowledge base survives across engine instances."""
    with tempfile.TemporaryDirectory() as tmpdir:
        kb_dir = f"{tmpdir}/kb"
        
        # Instance 1: learn
        engine1 = EvolutionEngine(knowledge_dir=kb_dir)
        engine1.learn(_make_trace_with_failure())
        count1 = len(engine1.kb.lessons)
        
        # Instance 2: load from disk
        engine2 = EvolutionEngine(knowledge_dir=kb_dir)
        assert len(engine2.kb.lessons) == count1
        assert engine2.kb.trace_count == 1


def test_suggest_returns_high_confidence():
    """suggest() returns lessons above confidence threshold."""
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = EvolutionEngine(knowledge_dir=f"{tmpdir}/kb")
        
        # Learn from multiple traces to build confidence
        for _ in range(5):
            engine.learn(_make_trace_with_failure())
        
        suggestions = engine.suggest(min_confidence=0.6)
        assert len(suggestions) >= 1
        assert all(s.confidence >= 0.6 for s in suggestions)
        # Should be sorted by confidence desc
        for i in range(len(suggestions) - 1):
            assert suggestions[i].confidence >= suggestions[i + 1].confidence


def test_summary_readable():
    """summary() produces a readable report."""
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = EvolutionEngine(knowledge_dir=f"{tmpdir}/kb")
        engine.learn(_make_trace_with_failure())
        
        text = engine.summary()
        assert "Evolution Knowledge Base" in text
        assert "Traces analyzed" in text


def test_reflection_report():
    """Reflection generates a readable report."""
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = EvolutionEngine(knowledge_dir=f"{tmpdir}/kb")
        reflection = engine.reflect(_make_trace_with_failure())
        
        report = reflection.to_report()
        assert "Reflection Report" in report
        assert "fragile" in report


def test_detect_trends():
    """detect_trends identifies recurring issues."""
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = EvolutionEngine(knowledge_dir=f"{tmpdir}/kb")
        
        # Learn from same failure 5 times
        for _ in range(5):
            engine.learn(_make_trace_with_failure())
        
        trends = engine.detect_trends()
        assert len(trends) >= 1
        recurring = [t for t in trends if t["type"] == "recurring_failure"]
        assert len(recurring) >= 1
