"""Version comparison, diff, and regression detection."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from agentguard.core.trace import ExecutionTrace
from agentguard.core.eval_schema import EvaluationResult, RuleResult, RuleVerdict


@dataclass
class DiffItem:
    """A single difference between two runs."""
    field: str
    baseline: Any
    candidate: Any
    delta: Optional[float] = None
    verdict: str = "neutral"  # improved, regressed, neutral

    def to_dict(self) -> dict:
        return {"field": self.field, "baseline": self.baseline, 
                "candidate": self.candidate, "delta": self.delta, "verdict": self.verdict}


@dataclass
class ComparisonResult:
    """Result of comparing two trace/eval runs."""
    baseline_id: str = ""
    candidate_id: str = ""
    baseline_version: str = ""
    candidate_version: str = ""
    diffs: list[DiffItem] = field(default_factory=list)
    baseline_eval: Optional[EvaluationResult] = None
    candidate_eval: Optional[EvaluationResult] = None

    @property
    def improved(self) -> int:
        return sum(1 for d in self.diffs if d.verdict == "improved")

    @property
    def regressed(self) -> int:
        return sum(1 for d in self.diffs if d.verdict == "regressed")

    @property
    def recommendation(self) -> str:
        if self.regressed > 0:
            return "review_before_deploy"
        if self.improved > 0:
            return "safe_to_deploy"
        return "no_change"

    def to_dict(self) -> dict:
        return {
            "baseline": {"id": self.baseline_id, "version": self.baseline_version},
            "candidate": {"id": self.candidate_id, "version": self.candidate_version},
            "improved": self.improved,
            "regressed": self.regressed,
            "recommendation": self.recommendation,
            "diffs": [d.to_dict() for d in self.diffs],
        }

    def to_report(self) -> str:
        lines = [
            "# Regression Report",
            "",
            f"- **Baseline:** {self.baseline_version} ({self.baseline_id})",
            f"- **Candidate:** {self.candidate_version} ({self.candidate_id})",
            f"- **Improved:** {self.improved}",
            f"- **Regressed:** {self.regressed}",
            f"- **Recommendation:** {self.recommendation}",
            "",
            "## Diffs",
            "",
        ]
        for d in self.diffs:
            icon = "📈" if d.verdict == "improved" else "📉" if d.verdict == "regressed" else "➡️"
            delta_str = f" (Δ {d.delta:+.2f})" if d.delta is not None else ""
            lines.append(f"- {icon} **{d.field}**: {d.baseline} → {d.candidate}{delta_str}")
        return "\n".join(lines)


def compare_traces(baseline: ExecutionTrace, candidate: ExecutionTrace) -> ComparisonResult:
    """Compare two execution traces."""
    result = ComparisonResult(
        baseline_id=baseline.trace_id,
        candidate_id=candidate.trace_id,
    )
    
    # Compare duration
    if baseline.duration_ms and candidate.duration_ms:
        delta = candidate.duration_ms - baseline.duration_ms
        verdict = "improved" if delta < -100 else ("regressed" if delta > 500 else "neutral")
        result.diffs.append(DiffItem(
            field="duration_ms", baseline=round(baseline.duration_ms),
            candidate=round(candidate.duration_ms), delta=delta, verdict=verdict
        ))
    
    # Compare span counts
    b_agents = len(baseline.agent_spans)
    c_agents = len(candidate.agent_spans)
    if b_agents != c_agents:
        result.diffs.append(DiffItem(field="agent_count", baseline=b_agents, candidate=c_agents))
    
    b_tools = len(baseline.tool_spans)
    c_tools = len(candidate.tool_spans)
    if b_tools != c_tools:
        result.diffs.append(DiffItem(field="tool_count", baseline=b_tools, candidate=c_tools))
    
    # Compare error rates
    b_errors = sum(1 for s in baseline.spans if s.status.value == "failed")
    c_errors = sum(1 for s in candidate.spans if s.status.value == "failed")
    if b_errors != c_errors:
        verdict = "improved" if c_errors < b_errors else "regressed"
        result.diffs.append(DiffItem(
            field="error_count", baseline=b_errors, candidate=c_errors,
            delta=c_errors - b_errors, verdict=verdict
        ))
    
    return result


def compare_evals(baseline: EvaluationResult, candidate: EvaluationResult) -> ComparisonResult:
    """Compare two evaluation results."""
    result = ComparisonResult(
        baseline_id=baseline.trace_id,
        candidate_id=candidate.trace_id,
        baseline_version=baseline.agent_version,
        candidate_version=candidate.agent_version,
        baseline_eval=baseline,
        candidate_eval=candidate,
    )
    
    # Compare pass rates
    b_rate = baseline.passed / max(baseline.total, 1)
    c_rate = candidate.passed / max(candidate.total, 1)
    delta = c_rate - b_rate
    verdict = "improved" if delta > 0.05 else ("regressed" if delta < -0.05 else "neutral")
    result.diffs.append(DiffItem(
        field="pass_rate", baseline=f"{b_rate:.0%}", candidate=f"{c_rate:.0%}",
        delta=delta, verdict=verdict
    ))
    
    # Compare individual rules
    b_rules = {r.name: r for r in baseline.rules}
    c_rules = {r.name: r for r in candidate.rules}
    
    for name in set(list(b_rules.keys()) + list(c_rules.keys())):
        b = b_rules.get(name)
        c = c_rules.get(name)
        if b and c and b.verdict != c.verdict:
            if c.verdict == RuleVerdict.PASS and b.verdict == RuleVerdict.FAIL:
                verdict = "improved"
            elif c.verdict == RuleVerdict.FAIL and b.verdict == RuleVerdict.PASS:
                verdict = "regressed"
            else:
                verdict = "neutral"
            result.diffs.append(DiffItem(
                field=f"rule:{name}", baseline=b.verdict.value, 
                candidate=c.verdict.value, verdict=verdict
            ))
    
    return result
