"""Span tree utilities — robust tree construction, traversal, and validation.

Handles edge cases in span trees:
- Cyclic references (parent pointing to child)
- Orphan spans (parent_span_id pointing to non-existent span)
- Deep nesting (prevent stack overflow)
- Multiple roots
- Tree statistics (depth, width, fan-out)
"""

from __future__ import annotations

from dataclasses import dataclass

from agentguard.core.trace import ExecutionTrace, Span, SpanStatus


@dataclass
class TreeStats:
    """Statistics about the span tree structure."""
    depth: int  # max depth from root to leaf
    width: int  # max number of siblings at any level
    root_count: int
    node_count: int
    orphan_count: int  # spans with non-existent parent
    leaf_count: int  # spans with no children
    avg_fan_out: float  # average children per non-leaf

    def to_dict(self) -> dict:
        return {
            "depth": self.depth,
            "width": self.width,
            "root_count": self.root_count,
            "node_count": self.node_count,
            "orphan_count": self.orphan_count,
            "leaf_count": self.leaf_count,
            "avg_fan_out": round(self.avg_fan_out, 2),
        }


def compute_tree_stats(trace: ExecutionTrace) -> TreeStats:
    """Compute tree structure statistics."""
    span_map = {s.span_id: s for s in trace.spans}
    children_map: dict[str, list[str]] = {}

    roots = []
    orphans = []

    for s in trace.spans:
        if s.parent_span_id:
            if s.parent_span_id in span_map:
                children_map.setdefault(s.parent_span_id, []).append(s.span_id)
            else:
                orphans.append(s.span_id)
                roots.append(s.span_id)  # treat orphans as roots
        else:
            roots.append(s.span_id)

    # Compute depth (iterative to avoid stack overflow)
    def max_depth(root_id: str) -> int:
        depth = 0
        stack = [(root_id, 1)]
        visited = set()
        while stack:
            nid, d = stack.pop()
            if nid in visited:
                continue  # cycle detected
            visited.add(nid)
            depth = max(depth, d)
            for child_id in children_map.get(nid, []):
                if child_id not in visited:
                    stack.append((child_id, d + 1))
        return depth

    total_depth = max((max_depth(r) for r in roots), default=0)

    # Width: max siblings at any level
    max_width = max((len(kids) for kids in children_map.values()), default=0)

    # Leaf count
    all_parents = set(children_map.keys())
    leaf_count = sum(1 for s in trace.spans if s.span_id not in all_parents)

    # Fan-out
    non_leaf_count = len(children_map)
    total_children = sum(len(kids) for kids in children_map.values())
    avg_fan_out = total_children / max(non_leaf_count, 1)

    return TreeStats(
        depth=total_depth,
        width=max_width,
        root_count=len(roots),
        node_count=len(trace.spans),
        orphan_count=len(orphans),
        leaf_count=leaf_count,
        avg_fan_out=avg_fan_out,
    )


def detect_cycles(trace: ExecutionTrace) -> list[list[str]]:
    """Detect circular parent references in the span tree.

    Returns list of cycles, where each cycle is a list of span_ids.
    """
    span_map = {s.span_id: s for s in trace.spans}
    cycles = []
    visited_global = set()

    for s in trace.spans:
        if s.span_id in visited_global:
            continue

        path = []
        path_set = set()
        current_id: str | None = s.span_id

        while current_id and current_id not in visited_global:
            if current_id in path_set:
                # Found a cycle
                cycle_start = path.index(current_id)
                cycle = path[cycle_start:] + [current_id]
                cycles.append(cycle)
                break

            path.append(current_id)
            path_set.add(current_id)

            span = span_map.get(current_id)
            current_id = span.parent_span_id if span else None

        visited_global.update(path_set)

    return cycles


def find_orphans(trace: ExecutionTrace) -> list[Span]:
    """Find spans whose parent_span_id references a non-existent span."""
    span_ids = {s.span_id for s in trace.spans}
    return [s for s in trace.spans if s.parent_span_id and s.parent_span_id not in span_ids]


def find_roots(trace: ExecutionTrace) -> list[Span]:
    """Find root spans (no parent or parent doesn't exist)."""
    span_ids = {s.span_id for s in trace.spans}
    return [s for s in trace.spans
            if s.parent_span_id is None or s.parent_span_id not in span_ids]


def tree_to_text(trace: ExecutionTrace, indent: str = "  ") -> str:
    """Render the span tree as indented text.

    Handles orphans and cycles gracefully.
    """
    span_map = {s.span_id: s for s in trace.spans}
    children_map: dict[str, list[str]] = {}

    for s in trace.spans:
        if s.parent_span_id and s.parent_span_id in span_map:
            children_map.setdefault(s.parent_span_id, []).append(s.span_id)

    roots = find_roots(trace)
    lines = []
    visited = set()

    def render(span_id: str, depth: int) -> None:
        if span_id in visited or depth > 50:
            lines.append(f"{indent * depth}⚠ [cycle or deep nesting]")
            return
        visited.add(span_id)

        span = span_map.get(span_id)
        if not span:
            return

        status_icon = {
            SpanStatus.COMPLETED: "✅",
            SpanStatus.FAILED: "❌",
            SpanStatus.RUNNING: "🔄",
            SpanStatus.TIMEOUT: "⏰",
        }.get(span.status, "❓")

        dur = f" ({span.duration_ms:.0f}ms)" if span.duration_ms else ""
        lines.append(f"{indent * depth}{status_icon} [{span.span_type.value}] {span.name}{dur}")

        for child_id in children_map.get(span_id, []):
            render(child_id, depth + 1)

    for root in roots:
        render(root.span_id, 0)

    return "\n".join(lines) if lines else "(empty trace)"
