"""Error classification — categorize and analyze errors in traces.

Classifies errors into categories:
- TRANSIENT: Connection, timeout, rate limit (retryable)
- PERMANENT: Auth, validation, not found (not retryable)
- RESOURCE: OOM, disk full, quota exceeded
- LOGIC: Assertion, type error, value error
- UNKNOWN: Unclassified
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from agentguard.core.trace import ExecutionTrace, Span, SpanStatus


class ErrorCategory(str, Enum):
    TRANSIENT = "transient"
    PERMANENT = "permanent"
    RESOURCE = "resource"
    LOGIC = "logic"
    UNKNOWN = "unknown"


_TRANSIENT_PATTERNS = [
    r"connection.*refused", r"timeout", r"rate.?limit", r"too many requests",
    r"503", r"502", r"504", r"429", r"connection.*reset", r"broken.*pipe",
    r"temporary", r"retry", r"unavailable",
]

_PERMANENT_PATTERNS = [
    r"401", r"403", r"404", r"authentication", r"authorization",
    r"not.?found", r"forbidden", r"invalid.*key", r"permission",
]

_RESOURCE_PATTERNS = [
    r"out.?of.?memory", r"oom", r"disk.*full", r"quota.*exceeded",
    r"no.*space", r"resource.*exhausted", r"memory.*error",
]

_LOGIC_PATTERNS = [
    r"assertion.*error", r"type.*error", r"value.*error",
    r"key.*error", r"index.*error", r"attribute.*error",
    r"name.*error", r"import.*error",
]


def classify_error(error_msg: str) -> ErrorCategory:
    """Classify an error message into a category."""
    if not error_msg:
        return ErrorCategory.UNKNOWN
    
    lower = error_msg.lower()
    
    for pattern in _TRANSIENT_PATTERNS:
        if re.search(pattern, lower):
            return ErrorCategory.TRANSIENT
    
    for pattern in _PERMANENT_PATTERNS:
        if re.search(pattern, lower):
            return ErrorCategory.PERMANENT
    
    for pattern in _RESOURCE_PATTERNS:
        if re.search(pattern, lower):
            return ErrorCategory.RESOURCE
    
    for pattern in _LOGIC_PATTERNS:
        if re.search(pattern, lower):
            return ErrorCategory.LOGIC
    
    return ErrorCategory.UNKNOWN


@dataclass
class ErrorReport:
    """Error analysis for a trace."""
    total_errors: int
    by_category: dict[str, int]
    retryable_count: int
    errors: list[dict]
    
    def to_dict(self) -> dict:
        return {
            "total_errors": self.total_errors,
            "by_category": self.by_category,
            "retryable_count": self.retryable_count,
            "errors": self.errors[:20],
        }
    
    def to_report(self) -> str:
        lines = [
            f"# Error Analysis ({self.total_errors} errors)",
            f"Retryable: {self.retryable_count} · Non-retryable: {self.total_errors - self.retryable_count}",
            "",
        ]
        for cat, count in sorted(self.by_category.items(), key=lambda x: -x[1]):
            icon = {"transient": "🔄", "permanent": "🔒", "resource": "💾", "logic": "🐛", "unknown": "❓"}.get(cat, "❓")
            lines.append(f"{icon} **{cat}**: {count}")
        
        if self.errors:
            lines.append("")
            for e in self.errors[:10]:
                lines.append(f"  [{e['category']}] {e['agent']}: {e['error'][:60]}")
        
        return "\n".join(lines)


def analyze_errors(trace: ExecutionTrace) -> ErrorReport:
    """Analyze all errors in a trace with classification."""
    errors = []
    by_category: dict[str, int] = {}
    
    for span in trace.spans:
        if span.status == SpanStatus.FAILED and span.error:
            cat = classify_error(span.error)
            errors.append({
                "agent": span.name,
                "error": span.error,
                "category": cat.value,
                "retryable": cat == ErrorCategory.TRANSIENT,
                "span_type": span.span_type.value,
            })
            by_category[cat.value] = by_category.get(cat.value, 0) + 1
    
    retryable = sum(1 for e in errors if e["retryable"])
    
    return ErrorReport(
        total_errors=len(errors),
        by_category=by_category,
        retryable_count=retryable,
        errors=errors,
    )
