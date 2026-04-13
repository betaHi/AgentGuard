"""Span-level diff — detailed field-by-field comparison between corresponding spans.

When comparing two traces of the same pipeline, this module matches spans by name
and compares their fields to identify exactly what changed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agentguard.core.trace import ExecutionTrace, Span


@dataclass
class FieldDiff:
    """A single field difference between two spans."""
    field_name: str
    value_a: Any
    value_b: Any
    change_type: str  # "added", "removed", "modified", "unchanged"

    def to_dict(self) -> dict:
        return {
            "field": self.field_name,
            "before": self.value_a,
            "after": self.value_b,
            "change": self.change_type,
        }


@dataclass
class SpanMatch:
    """A matched pair of spans from two traces."""
    name: str
    span_a: Span | None
    span_b: Span | None
    match_type: str  # "matched", "added", "removed"
    field_diffs: list[FieldDiff] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "match_type": self.match_type,
            "field_diffs": [d.to_dict() for d in self.field_diffs],
        }


@dataclass
class SpanDiffReport:
    """Complete span-level diff between two traces."""
    matches: list[SpanMatch]
    added_count: int
    removed_count: int
    modified_count: int
    unchanged_count: int

    def to_dict(self) -> dict:
        return {
            "added": self.added_count,
            "removed": self.removed_count,
            "modified": self.modified_count,
            "unchanged": self.unchanged_count,
            "matches": [m.to_dict() for m in self.matches if m.match_type != "matched" or m.field_diffs],
        }

    def to_report(self) -> str:
        lines = [
            "# Span-Level Diff",
            "",
            f"- **Added:** {self.added_count} spans",
            f"- **Removed:** {self.removed_count} spans",
            f"- **Modified:** {self.modified_count} spans",
            f"- **Unchanged:** {self.unchanged_count} spans",
            "",
        ]

        for m in self.matches:
            if m.match_type == "added":
                lines.append(f"➕ **{m.name}** (new span)")
            elif m.match_type == "removed":
                lines.append(f"➖ **{m.name}** (removed)")
            elif m.field_diffs:
                lines.append(f"🔄 **{m.name}**")
                for d in m.field_diffs:
                    lines.append(f"   {d.field_name}: {d.value_a} → {d.value_b}")

        return "\n".join(lines)


def _compare_span_fields(a: Span, b: Span) -> list[FieldDiff]:
    """Compare two spans field by field."""
    diffs = []

    fields_to_compare = [
        ("status", a.status.value, b.status.value),
        ("span_type", a.span_type.value, b.span_type.value),
        ("error", a.error, b.error),
        ("retry_count", a.retry_count, b.retry_count),
        ("token_count", a.token_count, b.token_count),
        ("estimated_cost_usd", a.estimated_cost_usd, b.estimated_cost_usd),
        ("failure_handled", a.failure_handled, b.failure_handled),
    ]

    # Duration comparison (allow some tolerance)
    dur_a = a.duration_ms
    dur_b = b.duration_ms
    if dur_a is not None and dur_b is not None and abs(dur_a - dur_b) > max(dur_a * 0.1, 100):  # >10% or >100ms
        diffs.append(FieldDiff("duration_ms", round(dur_a, 1), round(dur_b, 1), "modified"))

    for name, val_a, val_b in fields_to_compare:
        if val_a != val_b:
            diffs.append(FieldDiff(name, val_a, val_b, "modified"))

    # Input/output key comparison
    in_keys_a = set((a.input_data or {}).keys()) if isinstance(a.input_data, dict) else set()
    in_keys_b = set((b.input_data or {}).keys()) if isinstance(b.input_data, dict) else set()
    if in_keys_a != in_keys_b:
        diffs.append(FieldDiff("input_keys", sorted(in_keys_a), sorted(in_keys_b), "modified"))

    out_keys_a = set((a.output_data or {}).keys()) if isinstance(a.output_data, dict) else set()
    out_keys_b = set((b.output_data or {}).keys()) if isinstance(b.output_data, dict) else set()
    if out_keys_a != out_keys_b:
        diffs.append(FieldDiff("output_keys", sorted(out_keys_a), sorted(out_keys_b), "modified"))

    return diffs


def diff_spans(trace_a: ExecutionTrace, trace_b: ExecutionTrace) -> SpanDiffReport:
    """Perform span-level diff between two traces.

    Matches spans by name and compares their fields.
    """
    spans_a = {s.name: s for s in trace_a.spans}
    spans_b = {s.name: s for s in trace_b.spans}

    all_names = sorted(set(spans_a.keys()) | set(spans_b.keys()))

    matches = []
    added = 0
    removed = 0
    modified = 0
    unchanged = 0

    for name in all_names:
        a = spans_a.get(name)
        b = spans_b.get(name)

        if a and b:
            field_diffs = _compare_span_fields(a, b)
            match_type = "matched"
            if field_diffs:
                modified += 1
            else:
                unchanged += 1
            matches.append(SpanMatch(name=name, span_a=a, span_b=b, match_type=match_type, field_diffs=field_diffs))
        elif a and not b:
            removed += 1
            matches.append(SpanMatch(name=name, span_a=a, span_b=None, match_type="removed"))
        else:
            added += 1
            matches.append(SpanMatch(name=name, span_a=None, span_b=b, match_type="added"))

    return SpanDiffReport(
        matches=matches,
        added_count=added,
        removed_count=removed,
        modified_count=modified,
        unchanged_count=unchanged,
    )
