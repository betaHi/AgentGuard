"""SLA checker — verify traces meet service level agreements.

Define SLAs as a set of constraints:
- Max duration (P95 < 10s)
- Min success rate (> 99%)
- Max cost per trace ($0.50)
- Max error rate per agent (< 5%)
- Context preservation (> 90%)

Check individual traces or batches against SLAs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from agentguard.core.trace import ExecutionTrace, SpanStatus
from agentguard.metrics import extract_metrics
from agentguard.scoring import score_trace


@dataclass
class SLAConstraint:
    """A single SLA constraint."""
    name: str
    check_fn_name: str  # internal key for the check
    threshold: float
    operator: str  # "lt", "gt", "lte", "gte"
    severity: str = "error"  # what happens when violated
    
    def to_dict(self) -> dict:
        return {"name": self.name, "threshold": self.threshold, "operator": self.operator}


@dataclass
class SLAViolation:
    """A single SLA violation."""
    constraint: str
    actual_value: float
    threshold: float
    severity: str
    message: str
    
    def to_dict(self) -> dict:
        return {
            "constraint": self.constraint,
            "actual": self.actual_value,
            "threshold": self.threshold,
            "severity": self.severity,
            "message": self.message,
        }


@dataclass
class SLAResult:
    """Result of checking a trace against SLAs."""
    passed: bool
    violations: list[SLAViolation]
    checks_run: int
    
    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "violations": [v.to_dict() for v in self.violations],
            "checks_run": self.checks_run,
        }
    
    def to_report(self) -> str:
        status = "✅ PASSED" if self.passed else "❌ FAILED"
        lines = [
            f"# SLA Check: {status}",
            f"Checks run: {self.checks_run}, Violations: {len(self.violations)}",
            "",
        ]
        for v in self.violations:
            icon = "🔴" if v.severity == "error" else "🟡"
            lines.append(f"{icon} **{v.constraint}**: {v.message}")
        return "\n".join(lines)


class SLAChecker:
    """Check traces against defined SLAs."""
    
    def __init__(self) -> None:
        self._constraints: list[tuple[str, str, float, str]] = []
    
    def max_duration_ms(self, threshold: float, severity: str = "error") -> SLAChecker:
        """Trace duration must be below threshold."""
        self._constraints.append(("max_duration", "duration_ms", threshold, severity))
        return self
    
    def min_success_rate(self, threshold: float, severity: str = "error") -> SLAChecker:
        """Span success rate must be above threshold."""
        self._constraints.append(("min_success_rate", "success_rate", threshold, severity))
        return self
    
    def max_cost_usd(self, threshold: float, severity: str = "warning") -> SLAChecker:
        """Total cost must be below threshold."""
        self._constraints.append(("max_cost", "cost_usd", threshold, severity))
        return self
    
    def min_score(self, threshold: float, severity: str = "error") -> SLAChecker:
        """Quality score must be above threshold."""
        self._constraints.append(("min_score", "score", threshold, severity))
        return self
    
    def max_error_rate(self, threshold: float, severity: str = "error") -> SLAChecker:
        """Error rate must be below threshold."""
        self._constraints.append(("max_error_rate", "error_rate", threshold, severity))
        return self
    
    def check(self, trace: ExecutionTrace) -> SLAResult:
        """Check a trace against all defined SLAs."""
        violations = []
        metrics = extract_metrics(trace)
        score = score_trace(trace)
        
        for name, metric_key, threshold, severity in self._constraints:
            actual: Optional[float] = None
            violated = False
            
            if metric_key == "duration_ms":
                actual = trace.duration_ms or 0
                violated = actual > threshold
            elif metric_key == "success_rate":
                actual = metrics.success_rate
                violated = actual < threshold
            elif metric_key == "cost_usd":
                actual = metrics.total_cost_usd
                violated = actual > threshold
            elif metric_key == "score":
                actual = score.overall
                violated = actual < threshold
            elif metric_key == "error_rate":
                actual = metrics.error_rate
                violated = actual > threshold
            
            if violated and actual is not None:
                op = "above" if name.startswith("max") else "below"
                violations.append(SLAViolation(
                    constraint=name,
                    actual_value=round(actual, 3),
                    threshold=threshold,
                    severity=severity,
                    message=f"{name}: {actual:.3f} is {op} threshold {threshold}",
                ))
        
        return SLAResult(
            passed=len(violations) == 0,
            violations=violations,
            checks_run=len(self._constraints),
        )
    
    def check_batch(self, traces: list[ExecutionTrace]) -> dict:
        """Check multiple traces. Returns aggregate results."""
        results = [self.check(t) for t in traces]
        passed = sum(1 for r in results if r.passed)
        total_violations = sum(len(r.violations) for r in results)
        
        return {
            "traces_checked": len(traces),
            "traces_passed": passed,
            "traces_failed": len(traces) - passed,
            "pass_rate": passed / max(len(traces), 1),
            "total_violations": total_violations,
        }
