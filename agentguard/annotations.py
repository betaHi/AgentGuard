"""Span annotations — structured semantic tags for trace enrichment.

Annotations add structured metadata to spans beyond simple key-value pairs:
- Severity levels (info, warning, error, critical)
- Categories (performance, correctness, security, quality)
- Links to related spans, issues, or external resources
- Time-stamped notes from humans or automated systems
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from agentguard.core.trace import ExecutionTrace, Span


class AnnotationSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AnnotationCategory(StrEnum):
    PERFORMANCE = "performance"
    CORRECTNESS = "correctness"
    SECURITY = "security"
    QUALITY = "quality"
    CONTEXT = "context"
    CUSTOM = "custom"


@dataclass
class Annotation:
    """A structured annotation on a span."""
    message: str
    severity: AnnotationSeverity = AnnotationSeverity.INFO
    category: AnnotationCategory = AnnotationCategory.CUSTOM
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    author: str = "system"  # "system", "human", agent name
    related_span_id: str | None = None
    link: str | None = None  # URL to issue, doc, etc.
    data: dict | None = None  # arbitrary structured data

    def to_dict(self) -> dict:
        d = {
            "message": self.message,
            "severity": self.severity.value,
            "category": self.category.value,
            "timestamp": self.timestamp,
            "author": self.author,
        }
        if self.related_span_id:
            d["related_span_id"] = self.related_span_id
        if self.link:
            d["link"] = self.link
        if self.data:
            d["data"] = self.data
        return d

    @classmethod
    def from_dict(cls, data: dict) -> Annotation:
        return cls(
            message=data["message"],
            severity=AnnotationSeverity(data.get("severity", "info")),
            category=AnnotationCategory(data.get("category", "custom")),
            timestamp=data.get("timestamp", ""),
            author=data.get("author", "system"),
            related_span_id=data.get("related_span_id"),
            link=data.get("link"),
            data=data.get("data"),
        )


class AnnotationStore:
    """Store and query annotations for spans in a trace."""

    def __init__(self) -> None:
        self._annotations: dict[str, list[Annotation]] = {}  # span_id -> annotations

    def annotate(self, span_id: str, annotation: Annotation) -> None:
        """Add an annotation to a span."""
        self._annotations.setdefault(span_id, []).append(annotation)

    def annotate_span(
        self,
        span: Span,
        message: str,
        severity: AnnotationSeverity = AnnotationSeverity.INFO,
        category: AnnotationCategory = AnnotationCategory.CUSTOM,
        author: str = "system",
        **kwargs: Any,
    ) -> Annotation:
        """Convenience method to annotate a span directly."""
        ann = Annotation(
            message=message, severity=severity, category=category,
            author=author, **kwargs,
        )
        self.annotate(span.span_id, ann)
        return ann

    def get(self, span_id: str) -> list[Annotation]:
        """Get all annotations for a span."""
        return self._annotations.get(span_id, [])

    def get_by_severity(self, severity: AnnotationSeverity) -> list[tuple[str, Annotation]]:
        """Get all annotations of a given severity."""
        results = []
        for span_id, anns in self._annotations.items():
            for ann in anns:
                if ann.severity == severity:
                    results.append((span_id, ann))
        return results

    def get_by_category(self, category: AnnotationCategory) -> list[tuple[str, Annotation]]:
        """Get all annotations of a given category."""
        results = []
        for span_id, anns in self._annotations.items():
            for ann in anns:
                if ann.category == category:
                    results.append((span_id, ann))
        return results

    @property
    def count(self) -> int:
        return sum(len(anns) for anns in self._annotations.values())

    def to_dict(self) -> dict:
        return {
            span_id: [a.to_dict() for a in anns]
            for span_id, anns in self._annotations.items()
        }

    @classmethod
    def from_dict(cls, data: dict) -> AnnotationStore:
        store = cls()
        for span_id, anns in data.items():
            for ann_data in anns:
                store.annotate(span_id, Annotation.from_dict(ann_data))
        return store

    def summary(self) -> dict:
        """Summary statistics."""
        by_severity: dict[str, int] = {}
        by_category: dict[str, int] = {}
        for anns in self._annotations.values():
            for ann in anns:
                by_severity[ann.severity.value] = by_severity.get(ann.severity.value, 0) + 1
                by_category[ann.category.value] = by_category.get(ann.category.value, 0) + 1
        return {
            "total": self.count,
            "by_severity": by_severity,
            "by_category": by_category,
            "spans_annotated": len(self._annotations),
        }


def auto_annotate(trace: ExecutionTrace) -> AnnotationStore:
    """Automatically annotate a trace with detected issues.

    Scans the trace for common problems and adds annotations:
    - Slow spans (> 2x average duration)
    - Failed spans with errors
    - Context loss at handoffs
    - Missing output data
    """
    store = AnnotationStore()

    # Collect duration stats
    durations = [s.duration_ms for s in trace.spans if s.duration_ms and s.duration_ms > 0]
    avg_duration = sum(durations) / max(len(durations), 1) if durations else 0

    for span in trace.spans:
        # Slow spans
        if span.duration_ms and avg_duration > 0 and span.duration_ms > avg_duration * 2:
            store.annotate_span(
                span,
                f"Slow span: {span.duration_ms:.0f}ms ({span.duration_ms / avg_duration:.1f}x average)",
                severity=AnnotationSeverity.WARNING,
                category=AnnotationCategory.PERFORMANCE,
            )

        # Failed spans
        if span.status.value == "failed":
            store.annotate_span(
                span,
                f"Span failed: {span.error or 'unknown error'}",
                severity=AnnotationSeverity.ERROR,
                category=AnnotationCategory.CORRECTNESS,
            )

        # Context loss at handoffs
        if span.context_dropped_keys:
            store.annotate_span(
                span,
                f"Context keys dropped: {span.context_dropped_keys}",
                severity=AnnotationSeverity.WARNING,
                category=AnnotationCategory.CONTEXT,
            )

        # Missing output on completed agents
        if (span.span_type.value == "agent" and
            span.status.value == "completed" and
            span.output_data is None):
            store.annotate_span(
                span,
                "Agent completed but produced no output data",
                severity=AnnotationSeverity.INFO,
                category=AnnotationCategory.QUALITY,
            )

    return store
