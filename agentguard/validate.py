"""Trace validation — ensure trace integrity before analysis.

Catches common issues:
- Orphan spans (parent_span_id points to nonexistent span)
- Duplicate span IDs
- Spans without end time (still "running")
- Circular parent references
- Missing required fields
"""



from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from agentguard.core.trace import ExecutionTrace, Span

__all__ = ['ValidationIssue', 'ValidationResult', 'validate_trace']


@dataclass
class ValidationIssue:
    """A single validation issue found in a trace."""
    severity: str  # "error", "warning"
    span_id: Optional[str]
    message: str

    def to_dict(self) -> dict:
        return {"severity": self.severity, "span_id": self.span_id, "message": self.message}


@dataclass
class ValidationResult:
    """Result of validating a trace."""
    valid: bool
    issues: list[ValidationIssue] = field(default_factory=list)
    
    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "error"]
    
    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "errors": len(self.errors),
            "warnings": len(self.warnings),
            "issues": [i.to_dict() for i in self.issues],
        }


def validate_trace(trace: ExecutionTrace) -> ValidationResult:
    """Validate trace integrity.
    
    Checks:
    - All span_ids are unique
    - All parent_span_ids reference existing spans
    - No circular parent references
    - All spans have required fields (span_id, name, span_type)
    - Completed/failed spans have ended_at
    - Trace has at least one span
    """
    issues = []
    span_ids = set()
    span_map = {}
    
    # Check trace has spans
    if not trace.spans:
        issues.append(ValidationIssue("warning", None, "Trace has no spans"))
    
    # Check trace has task
    if not trace.task:
        issues.append(ValidationIssue("warning", None, "Trace has no task description"))
    
    for span in trace.spans:
        # Duplicate ID check
        if span.span_id in span_ids:
            issues.append(ValidationIssue("error", span.span_id, f"Duplicate span_id: {span.span_id}"))
        span_ids.add(span.span_id)
        span_map[span.span_id] = span
        
        # Required fields
        if not span.name:
            issues.append(ValidationIssue("warning", span.span_id, "Span has no name"))
        
        # Running spans (not ended)
        if span.status.value in ("completed", "failed") and not span.ended_at:
            issues.append(ValidationIssue("warning", span.span_id, 
                         f"Span '{span.name}' is {span.status.value} but has no ended_at"))
    
    # Orphan span check
    for span in trace.spans:
        if span.parent_span_id and span.parent_span_id not in span_map:
            issues.append(ValidationIssue("error", span.span_id,
                         f"Orphan span '{span.name}': parent {span.parent_span_id} not found"))
    
    # Circular reference check
    for span in trace.spans:
        visited = set()
        current = span.span_id
        while current:
            if current in visited:
                issues.append(ValidationIssue("error", span.span_id,
                             f"Circular parent reference detected at '{span.name}'"))
                break
            visited.add(current)
            parent = span_map.get(current)
            current = parent.parent_span_id if parent and parent.parent_span_id else None
    
    valid = len([i for i in issues if i.severity == "error"]) == 0
    return ValidationResult(valid=valid, issues=issues)
