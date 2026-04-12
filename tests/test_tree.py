"""Tests for span tree utilities."""

import pytest
from agentguard.core.trace import ExecutionTrace, Span, SpanType, SpanStatus
from agentguard.tree import compute_tree_stats, detect_cycles, find_orphans, find_roots, tree_to_text


class TestTreeStats:
    def test_simple_tree(self):
        trace = ExecutionTrace(task="tree")
        trace.add_span(Span(span_id="root", name="root", span_type=SpanType.AGENT))
        trace.add_span(Span(span_id="c1", name="child1", parent_span_id="root"))
        trace.add_span(Span(span_id="c2", name="child2", parent_span_id="root"))
        trace.add_span(Span(span_id="gc1", name="grandchild", parent_span_id="c1"))
        
        stats = compute_tree_stats(trace)
        assert stats.depth == 3
        assert stats.root_count == 1
        assert stats.node_count == 4
        assert stats.leaf_count == 2  # child2 and grandchild
        assert stats.width == 2  # root has 2 children

    def test_flat_tree(self):
        trace = ExecutionTrace(task="flat")
        for i in range(5):
            trace.add_span(Span(span_id=f"s{i}", name=f"span_{i}"))
        stats = compute_tree_stats(trace)
        assert stats.depth == 1  # all roots
        assert stats.root_count == 5

    def test_empty(self):
        trace = ExecutionTrace(task="empty")
        stats = compute_tree_stats(trace)
        assert stats.depth == 0
        assert stats.node_count == 0


class TestDetectCycles:
    def test_no_cycles(self):
        trace = ExecutionTrace(task="acyclic")
        trace.add_span(Span(span_id="a", name="a"))
        trace.add_span(Span(span_id="b", name="b", parent_span_id="a"))
        assert detect_cycles(trace) == []

    def test_self_cycle(self):
        trace = ExecutionTrace(task="self")
        trace.add_span(Span(span_id="a", name="a", parent_span_id="a"))
        cycles = detect_cycles(trace)
        assert len(cycles) >= 1


class TestFindOrphans:
    def test_no_orphans(self):
        trace = ExecutionTrace(task="clean")
        trace.add_span(Span(span_id="root", name="root"))
        trace.add_span(Span(span_id="child", name="child", parent_span_id="root"))
        assert find_orphans(trace) == []

    def test_orphan_detected(self):
        trace = ExecutionTrace(task="orphan")
        trace.add_span(Span(span_id="a", name="a", parent_span_id="nonexistent"))
        orphans = find_orphans(trace)
        assert len(orphans) == 1
        assert orphans[0].span_id == "a"


class TestFindRoots:
    def test_single_root(self):
        trace = ExecutionTrace(task="single")
        trace.add_span(Span(span_id="root", name="root"))
        trace.add_span(Span(span_id="child", name="child", parent_span_id="root"))
        roots = find_roots(trace)
        assert len(roots) == 1

    def test_multiple_roots(self):
        trace = ExecutionTrace(task="multi")
        trace.add_span(Span(span_id="r1", name="root1"))
        trace.add_span(Span(span_id="r2", name="root2"))
        roots = find_roots(trace)
        assert len(roots) == 2


class TestTreeToText:
    def test_basic_render(self):
        trace = ExecutionTrace(task="render")
        trace.add_span(Span(span_id="root", name="orchestrator", span_type=SpanType.AGENT, status=SpanStatus.COMPLETED))
        trace.add_span(Span(span_id="c1", name="worker", span_type=SpanType.AGENT, parent_span_id="root", status=SpanStatus.FAILED))
        text = tree_to_text(trace)
        assert "orchestrator" in text
        assert "worker" in text
        assert "✅" in text  # completed
        assert "❌" in text  # failed

    def test_empty_trace(self):
        trace = ExecutionTrace(task="empty")
        text = tree_to_text(trace)
        assert "empty" in text.lower()
