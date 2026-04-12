"""Alert rules engine — define custom rules that trigger alerts on traces.

Provides a declarative rule system:
- Define rules as conditions on trace metrics
- Rules produce alerts with severity and context
- Rules can be combined (AND/OR)
- Built-in rules for common patterns
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional

from agentguard.core.trace import ExecutionTrace, SpanStatus
from agentguard.scoring import score_trace
from agentguard.metrics import extract_metrics


@dataclass
class Alert:
    """A triggered alert from a rule evaluation."""
    rule_name: str
    severity: str  # "info", "warning", "error", "critical"
    message: str
    trace_id: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    details: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "rule": self.rule_name,
            "severity": self.severity,
            "message": self.message,
            "trace_id": self.trace_id,
            "timestamp": self.timestamp,
            "details": self.details,
        }


AlertRule = Callable[[ExecutionTrace], Optional[Alert]]


def rule_score_below(threshold: float, severity: str = "warning") -> AlertRule:
    """Alert if trace score drops below threshold."""
    def check(trace: ExecutionTrace) -> Optional[Alert]:
        score = score_trace(trace)
        if score.overall < threshold:
            return Alert(
                rule_name=f"score_below_{threshold}",
                severity=severity,
                message=f"Trace score {score.overall:.0f} is below threshold {threshold}",
                trace_id=trace.trace_id,
                details={"score": score.overall, "grade": score.grade, "threshold": threshold},
            )
        return None
    return check


def rule_error_rate_above(threshold: float, severity: str = "error") -> AlertRule:
    """Alert if error rate exceeds threshold."""
    def check(trace: ExecutionTrace) -> Optional[Alert]:
        m = extract_metrics(trace)
        if m.error_rate > threshold:
            return Alert(
                rule_name=f"error_rate_above_{threshold}",
                severity=severity,
                message=f"Error rate {m.error_rate:.0%} exceeds {threshold:.0%}",
                trace_id=trace.trace_id,
                details={"error_rate": m.error_rate, "threshold": threshold},
            )
        return None
    return check


def rule_duration_above(max_ms: float, severity: str = "warning") -> AlertRule:
    """Alert if trace duration exceeds threshold."""
    def check(trace: ExecutionTrace) -> Optional[Alert]:
        dur = trace.duration_ms
        if dur and dur > max_ms:
            return Alert(
                rule_name=f"duration_above_{max_ms}ms",
                severity=severity,
                message=f"Duration {dur:.0f}ms exceeds {max_ms:.0f}ms",
                trace_id=trace.trace_id,
                details={"duration_ms": dur, "threshold_ms": max_ms},
            )
        return None
    return check


def rule_cost_above(max_usd: float, severity: str = "warning") -> AlertRule:
    """Alert if total cost exceeds threshold."""
    def check(trace: ExecutionTrace) -> Optional[Alert]:
        m = extract_metrics(trace)
        if m.total_cost_usd > max_usd:
            return Alert(
                rule_name=f"cost_above_{max_usd}",
                severity=severity,
                message=f"Cost ${m.total_cost_usd:.2f} exceeds ${max_usd:.2f}",
                trace_id=trace.trace_id,
                details={"cost_usd": m.total_cost_usd, "threshold_usd": max_usd},
            )
        return None
    return check


def rule_trace_failed(severity: str = "error") -> AlertRule:
    """Alert on any trace failure."""
    def check(trace: ExecutionTrace) -> Optional[Alert]:
        if trace.status == SpanStatus.FAILED:
            errors = [s.error for s in trace.spans if s.error]
            return Alert(
                rule_name="trace_failed",
                severity=severity,
                message=f"Trace failed: {errors[0][:100] if errors else 'unknown'}",
                trace_id=trace.trace_id,
                details={"errors": errors[:5]},
            )
        return None
    return check


class AlertEngine:
    """Engine for evaluating alert rules against traces."""
    
    def __init__(self) -> None:
        self._rules: list[AlertRule] = []
    
    def add_rule(self, rule: AlertRule) -> None:
        """Register an alert rule."""
        self._rules.append(rule)
    
    def evaluate(self, trace: ExecutionTrace) -> list[Alert]:
        """Evaluate all rules against a trace. Returns triggered alerts."""
        alerts = []
        for rule in self._rules:
            try:
                alert = rule(trace)
                if alert:
                    alerts.append(alert)
            except Exception:
                pass  # Rule evaluation errors are silently ignored
        return alerts
    
    def evaluate_batch(self, traces: list[ExecutionTrace]) -> list[Alert]:
        """Evaluate rules against multiple traces."""
        all_alerts = []
        for trace in traces:
            all_alerts.extend(self.evaluate(trace))
        return all_alerts
    
    @property
    def rule_count(self) -> int:
        return len(self._rules)
