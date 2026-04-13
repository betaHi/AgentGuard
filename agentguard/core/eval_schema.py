"""Evaluation result data models."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class RuleVerdict(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"
    ERROR = "error"


@dataclass
class RuleResult:
    """Result of a single rule assertion."""
    name: str
    rule_type: str
    verdict: RuleVerdict
    expected: Any = None
    actual: Any = None
    detail: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["verdict"] = self.verdict.value
        return d


@dataclass
class EvaluationResult:
    """Complete evaluation result for an agent execution."""
    trace_id: str = ""
    agent_name: str = ""
    agent_version: str = ""
    evaluated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    rules: list[RuleResult] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.rules if r.verdict == RuleVerdict.PASS)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.rules if r.verdict == RuleVerdict.FAIL)

    @property
    def total(self) -> int:
        return len(self.rules)

    @property
    def overall_verdict(self) -> RuleVerdict:
        if any(r.verdict == RuleVerdict.FAIL for r in self.rules):
            return RuleVerdict.FAIL
        if all(r.verdict == RuleVerdict.PASS for r in self.rules):
            return RuleVerdict.PASS
        return RuleVerdict.SKIP

    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "agent_name": self.agent_name,
            "agent_version": self.agent_version,
            "evaluated_at": self.evaluated_at,
            "overall": self.overall_verdict.value,
            "passed": self.passed,
            "failed": self.failed,
            "total": self.total,
            "rules": [r.to_dict() for r in self.rules],
            "metadata": self.metadata,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def to_report(self) -> str:
        """Generate a human-readable Markdown report."""
        lines = [
            "# Evaluation Report",
            "",
            f"- **Agent:** {self.agent_name} ({self.agent_version})",
            f"- **Trace:** {self.trace_id}",
            f"- **Result:** {self.passed}/{self.total} passed",
            f"- **Verdict:** {'✅ PASS' if self.overall_verdict == RuleVerdict.PASS else '❌ FAIL'}",
            "",
            "## Rules",
            "",
        ]
        for r in self.rules:
            icon = "✅" if r.verdict == RuleVerdict.PASS else "❌" if r.verdict == RuleVerdict.FAIL else "⏭️"
            lines.append(f"- {icon} **{r.name}** ({r.rule_type}): {r.verdict.value}")
            if r.detail:
                lines.append(f"  - {r.detail}")
            if r.verdict == RuleVerdict.FAIL:
                lines.append(f"  - Expected: `{r.expected}`, Got: `{r.actual}`")
        return "\n".join(lines)
