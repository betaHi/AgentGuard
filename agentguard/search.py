"""Trace search — full-text and structured search across traces.

Search through trace stores for:
- Spans matching text patterns
- Traces with specific errors
- Spans by tag combinations
- Traces by time range
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from agentguard.core.trace import ExecutionTrace


@dataclass
class SearchHit:
    """A search result."""
    trace_id: str
    span_id: str
    span_name: str
    span_type: str
    match_field: str  # which field matched
    match_text: str   # the matched text
    context: str = ""  # surrounding context

    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "span_name": self.span_name,
            "field": self.match_field,
            "match": self.match_text[:100],
        }


@dataclass
class SearchResults:
    """Collection of search results."""
    query: str
    hits: list[SearchHit]
    traces_searched: int
    spans_searched: int

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "hit_count": len(self.hits),
            "traces_searched": self.traces_searched,
            "spans_searched": self.spans_searched,
            "hits": [h.to_dict() for h in self.hits[:50]],
        }

    def to_report(self) -> str:
        lines = [
            f"# Search: '{self.query}'",
            f"Found {len(self.hits)} hits in {self.traces_searched} traces ({self.spans_searched} spans)",
            "",
        ]
        for hit in self.hits[:20]:
            lines.append(f"  📍 [{hit.span_type}] {hit.span_name} → {hit.match_field}: {hit.match_text[:80]}")
        if len(self.hits) > 20:
            lines.append(f"  ... and {len(self.hits) - 20} more")
        return "\n".join(lines)


def search_traces(
    traces: list[ExecutionTrace],
    query: str,
    fields: list[str] | None = None,
    case_sensitive: bool = False,
) -> SearchResults:
    """Search across multiple traces for matching text.

    Args:
        traces: Traces to search.
        query: Text to search for (supports regex).
        fields: Which fields to search (default: name, error, metadata, tags).
        case_sensitive: Whether search is case sensitive.
    """
    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        pattern = re.compile(query, flags)
    except re.error:
        pattern = re.compile(re.escape(query), flags)

    if fields is None:
        fields = ["name", "error", "metadata", "tags", "input_data", "output_data"]

    hits: list[SearchHit] = []
    total_spans = 0

    for trace in traces:
        for span in trace.spans:
            total_spans += 1

            # Search each field
            if "name" in fields and pattern.search(span.name):
                hits.append(SearchHit(
                    trace_id=trace.trace_id, span_id=span.span_id,
                    span_name=span.name, span_type=span.span_type.value,
                    match_field="name", match_text=span.name,
                ))

            if "error" in fields and span.error and pattern.search(span.error):
                hits.append(SearchHit(
                    trace_id=trace.trace_id, span_id=span.span_id,
                    span_name=span.name, span_type=span.span_type.value,
                    match_field="error", match_text=span.error,
                ))

            if "tags" in fields:
                for tag in span.tags:
                    if pattern.search(tag):
                        hits.append(SearchHit(
                            trace_id=trace.trace_id, span_id=span.span_id,
                            span_name=span.name, span_type=span.span_type.value,
                            match_field="tag", match_text=tag,
                        ))

            if "metadata" in fields:
                for key, val in span.metadata.items():
                    text = f"{key}={val}"
                    if pattern.search(text):
                        hits.append(SearchHit(
                            trace_id=trace.trace_id, span_id=span.span_id,
                            span_name=span.name, span_type=span.span_type.value,
                            match_field=f"metadata.{key}", match_text=text,
                        ))

    return SearchResults(
        query=query,
        hits=hits,
        traces_searched=len(traces),
        spans_searched=total_spans,
    )
