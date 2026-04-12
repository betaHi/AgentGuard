"""Trace manipulation — clone, merge, slice, and transform traces.

Useful for:
- Creating test variants
- Extracting sub-traces
- Merging traces from distributed systems
- Anonymizing traces for sharing
"""

from __future__ import annotations

import copy
import re
from typing import Optional, Set

from agentguard.core.trace import ExecutionTrace, Span, SpanType, SpanStatus


def clone_trace(trace: ExecutionTrace) -> ExecutionTrace:
    """Create a deep copy of a trace."""
    return copy.deepcopy(trace)


def slice_trace(
    trace: ExecutionTrace,
    span_names: Optional[Set[str]] = None,
    span_types: Optional[Set[SpanType]] = None,
    include_children: bool = True,
) -> ExecutionTrace:
    """Extract a subset of spans from a trace.
    
    Args:
        trace: Source trace.
        span_names: Include only these span names.
        span_types: Include only these span types.
        include_children: If True, include children of matched spans.
    """
    cloned = clone_trace(trace)
    
    # Determine which spans to keep
    keep_ids: set[str] = set()
    span_map = {s.span_id: s for s in cloned.spans}
    children_map: dict[str, list[str]] = {}
    
    for s in cloned.spans:
        if s.parent_span_id:
            children_map.setdefault(s.parent_span_id, []).append(s.span_id)
    
    for s in cloned.spans:
        match = True
        if span_names and s.name not in span_names:
            match = False
        if span_types and s.span_type not in span_types:
            match = False
        
        if match:
            keep_ids.add(s.span_id)
            
            if include_children:
                # BFS to include all descendants
                queue = [s.span_id]
                while queue:
                    current = queue.pop(0)
                    for child_id in children_map.get(current, []):
                        if child_id not in keep_ids:
                            keep_ids.add(child_id)
                            queue.append(child_id)
    
    cloned.spans = [s for s in cloned.spans if s.span_id in keep_ids]
    return cloned


def anonymize_trace(trace: ExecutionTrace) -> ExecutionTrace:
    """Anonymize a trace by removing sensitive data.
    
    Replaces:
    - Input/output data with key counts
    - Error messages with generic ones
    - Metadata values with types
    """
    cloned = clone_trace(trace)
    
    for s in cloned.spans:
        # Replace input/output with summary
        if isinstance(s.input_data, dict):
            s.input_data = {k: f"<{type(v).__name__}>" for k, v in s.input_data.items()}
        elif s.input_data is not None:
            s.input_data = f"<{type(s.input_data).__name__}>"
        
        if isinstance(s.output_data, dict):
            s.output_data = {k: f"<{type(v).__name__}>" for k, v in s.output_data.items()}
        elif s.output_data is not None:
            s.output_data = f"<{type(s.output_data).__name__}>"
        
        # Generalize errors
        if s.error:
            s.error = re.sub(r'[\w.-]+@[\w.-]+', '<email>', s.error)
            s.error = re.sub(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', '<ip>', s.error)
        
        # Remove metadata values
        s.metadata = {k: f"<{type(v).__name__}>" for k, v in s.metadata.items()}
    
    cloned.task = re.sub(r'[\w.-]+@[\w.-]+', '<email>', cloned.task)
    
    return cloned


def merge_traces(traces: list[ExecutionTrace], task: str = "merged") -> ExecutionTrace:
    """Merge multiple traces into a single trace.
    
    All spans from all traces are combined under a single trace ID.
    Useful for combining distributed trace fragments.
    """
    merged = ExecutionTrace(task=task)
    
    # Find earliest start and latest end
    starts = [t.started_at for t in traces if t.started_at]
    ends = [t.ended_at for t in traces if t.ended_at]
    
    if starts:
        merged.started_at = min(starts)
    if ends:
        merged.ended_at = max(ends)
    
    # Combine all spans
    for trace in traces:
        for span in trace.spans:
            span_copy = copy.deepcopy(span)
            span_copy.trace_id = merged.trace_id
            merged.spans.append(span_copy)
    
    # Set status
    has_failure = any(s.status == SpanStatus.FAILED for s in merged.spans)
    merged.status = SpanStatus.FAILED if has_failure else SpanStatus.COMPLETED
    
    return merged
