"""Regression harness — compare agent outputs against saved baselines.

The regression harness enables comparison of agent version outputs
against saved baselines. Note: this does not replay the actual execution
(which depends on external state); it compares outputs given the same inputs.

Usage:
    from agentguard.replay import ReplayEngine

    engine = ReplayEngine(traces_dir=".agentguard/traces")

    # Record a baseline
    engine.save_baseline("test-1", input_data={"topic": "AI"}, output_data={"articles": [...]})

    # Run candidate and compare
    result = engine.compare("test-1", candidate_output={"articles": [...]})
"""



from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agentguard.core.eval_schema import EvaluationResult
from agentguard.eval.compare import ComparisonResult
from agentguard.eval.rules import evaluate_rules
from agentguard.core.trace import ExecutionTrace, Span, SpanStatus, SpanType
from agentguard.scoring import score_trace

__all__ = ['ReplayCase', 'ReplayResult', 'ReplayEngine']


@dataclass
class ReplayCase:
    """A saved test case for replay."""
    name: str
    input_data: Any
    baseline_output: Any
    rules: list[dict] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "input_data": self.input_data,
            "baseline_output": self.baseline_output,
            "rules": self.rules,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ReplayCase:
        return cls(**{k: data[k] for k in cls.__dataclass_fields__ if k in data})


@dataclass
class ReplayResult:
    """Result of a single replay comparison."""
    case_name: str
    baseline_eval: EvaluationResult
    candidate_eval: EvaluationResult
    comparison: ComparisonResult
    verdict: str = ""  # improved, regressed, neutral

    def __post_init__(self):
        if not self.verdict:
            if self.comparison.regressed > 0:
                self.verdict = "regressed"
            elif self.comparison.improved > 0:
                self.verdict = "improved"
            else:
                self.verdict = "neutral"

    def to_dict(self) -> dict:
        return {
            "case": self.case_name,
            "verdict": self.verdict,
            "baseline": self.baseline_eval.to_dict(),
            "candidate": self.candidate_eval.to_dict(),
            "comparison": self.comparison.to_dict(),
        }


class ReplayEngine:
    """Engine for saving baselines and replaying test cases."""

    def __init__(self, baselines_dir: str = ".agentguard/baselines"):
        self.baselines_dir = Path(baselines_dir)

    def save_baseline(
        self,
        name: str,
        input_data: Any,
        output_data: Any,
        rules: list[dict] | None = None,
        metadata: dict | None = None,
    ) -> ReplayCase:
        """Save a baseline test case.

        Args:
            name: Unique name for this test case.
            input_data: Input that was given to the agent.
            output_data: Output that the agent produced (the "golden" output).
            rules: Evaluation rules to apply.
            metadata: Additional metadata.

        Returns:
            The saved ReplayCase.
        """
        case = ReplayCase(
            name=name,
            input_data=input_data,
            baseline_output=output_data,
            rules=rules or [],
            metadata=metadata or {},
        )

        self.baselines_dir.mkdir(parents=True, exist_ok=True)
        filepath = self.baselines_dir / f"{name}.json"
        filepath.write_text(json.dumps(case.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

        return case

    def load_baseline(self, name: str) -> ReplayCase | None:
        """Load a saved baseline test case."""
        filepath = self.baselines_dir / f"{name}.json"
        if not filepath.exists():
            return None
        data = json.loads(filepath.read_text(encoding="utf-8"))
        return ReplayCase.from_dict(data)

    def list_baselines(self) -> list[str]:
        """List all saved baseline names."""
        if not self.baselines_dir.exists():
            return []
        return [f.stem for f in self.baselines_dir.glob("*.json")]

    def compare(
        self,
        case_name: str,
        candidate_output: Any,
        rules: list[dict] | None = None,
    ) -> ReplayResult:
        """Compare candidate output against a saved baseline.

        Args:
            case_name: Name of the baseline to compare against.
            candidate_output: New agent output to evaluate.
            rules: Override rules (uses baseline rules if not provided).

        Returns:
            ReplayResult with comparison details.
        """
        case = self.load_baseline(case_name)
        if case is None:
            raise FileNotFoundError(f"Baseline not found: {case_name}")

        eval_rules = rules or case.rules

        # Evaluate baseline
        baseline_results = evaluate_rules(case.baseline_output, eval_rules) if eval_rules else []
        baseline_eval = EvaluationResult(
            agent_name=case_name,
            agent_version="baseline",
            rules=baseline_results,
        )

        # Evaluate candidate
        candidate_results = evaluate_rules(candidate_output, eval_rules) if eval_rules else []
        candidate_eval = EvaluationResult(
            agent_name=case_name,
            agent_version="candidate",
            rules=candidate_results,
        )

        # Build comparison
        from agentguard.eval.compare import compare_evals
        comparison = compare_evals(baseline_eval, candidate_eval)

        return ReplayResult(
            case_name=case_name,
            baseline_eval=baseline_eval,
            candidate_eval=candidate_eval,
            comparison=comparison,
        )

    def run_regression(
        self,
        agent_fn: Callable,
        cases: list[str] | None = None,
    ) -> list[ReplayResult]:
        """Run regression tests by replaying all (or selected) baselines.

        Args:
            agent_fn: The agent function to test. Should accept input_data and return output.
            cases: Specific case names to test (all if None).

        Returns:
            List of ReplayResults.
        """
        case_names = cases or self.list_baselines()
        results = []

        for name in case_names:
            case = self.load_baseline(name)
            if case is None:
                continue

            try:
                candidate_output = agent_fn(case.input_data)
                result = self.compare(name, candidate_output)
            except Exception:
                # Agent failed — create a failed result
                result = ReplayResult(
                    case_name=name,
                    baseline_eval=EvaluationResult(agent_name=name, agent_version="baseline"),
                    candidate_eval=EvaluationResult(agent_name=name, agent_version="candidate"),
                    comparison=ComparisonResult(),
                    verdict="regressed",
                )

            results.append(result)

        return results


# --- Merged from replay_v2.py ---

@dataclass
class AssertionResult:
    """Result of a single assertion on a span."""
    span_name: str
    assertion_name: str
    passed: bool
    message: str = ""

    def to_dict(self) -> dict:
        return {
            "span": self.span_name,
            "assertion": self.assertion_name,
            "passed": self.passed,
            "message": self.message,
        }


@dataclass
class AssertionReplayResult:
    """Result of replaying a trace with assertions."""
    trace_id: str
    total_assertions: int
    passed: int
    failed: int
    results: list[AssertionResult]

    @property
    def all_passed(self) -> bool:
        return self.failed == 0

    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "total": self.total_assertions,
            "passed": self.passed,
            "failed": self.failed,
            "all_passed": self.all_passed,
            "results": [r.to_dict() for r in self.results if not r.passed],
        }

    def to_report(self) -> str:
        status = "✅ ALL PASSED" if self.all_passed else f"❌ {self.failed} FAILED"
        lines = [
            f"# Replay: {status}",
            f"Assertions: {self.passed}/{self.total_assertions} passed",
            "",
        ]
        for r in self.results:
            if not r.passed:
                lines.append(f"❌ {r.span_name}: {r.assertion_name} — {r.message}")
        return "\n".join(lines)


class TraceReplay:
    """Replay a trace with configurable assertions."""

    def __init__(self) -> None:
        self._assertions: list[tuple[str, str, SpanAssertion]] = []  # (span_pattern, name, fn)
        self._global_assertions: list[tuple[str, SpanAssertion]] = []  # (name, fn)

    def assert_span(self, span_name: str, assertion_name: str, fn: SpanAssertion) -> TraceReplay:
        """Add an assertion for a specific span."""
        self._assertions.append((span_name, assertion_name, fn))
        return self

    def assert_all(self, assertion_name: str, fn: SpanAssertion) -> TraceReplay:
        """Add an assertion for all spans."""
        self._global_assertions.append((assertion_name, fn))
        return self

    def assert_completed(self, span_name: str) -> TraceReplay:
        """Assert a span completed successfully."""
        return self.assert_span(span_name, "completed",
                               lambda s: s.status == SpanStatus.COMPLETED)

    def assert_duration_below(self, span_name: str, max_ms: float) -> TraceReplay:
        """Assert a span's duration is below threshold."""
        return self.assert_span(span_name, f"duration<{max_ms}ms",
                               lambda s: (s.duration_ms or 0) < max_ms)

    def assert_has_output(self, span_name: str) -> TraceReplay:
        """Assert a span has output data."""
        return self.assert_span(span_name, "has_output",
                               lambda s: s.output_data is not None)

    def assert_no_errors(self) -> TraceReplay:
        """Assert no spans have errors."""
        return self.assert_all("no_errors", lambda s: s.error is None)

    def replay(self, trace: ExecutionTrace) -> AssertionReplayResult:
        """Replay a trace, running all assertions."""
        results: list[AssertionResult] = []

        span_map = {s.name: s for s in trace.spans}

        # Span-specific assertions
        for span_name, assertion_name, fn in self._assertions:
            span = span_map.get(span_name)
            if not span:
                results.append(AssertionResult(
                    span_name=span_name, assertion_name=assertion_name,
                    passed=False, message=f"Span '{span_name}' not found",
                ))
                continue

            try:
                passed = fn(span)
            except Exception:
                passed = False

            results.append(AssertionResult(
                span_name=span_name, assertion_name=assertion_name,
                passed=passed,
                message="" if passed else f"Assertion failed on '{span_name}'",
            ))

        # Global assertions
        for assertion_name, fn in self._global_assertions:
            for span in trace.spans:
                try:
                    passed = fn(span)
                except Exception:
                    passed = False

                if not passed:
                    results.append(AssertionResult(
                        span_name=span.name, assertion_name=assertion_name,
                        passed=False, message=f"Global assertion failed on '{span.name}'",
                    ))
                else:
                    results.append(AssertionResult(
                        span_name=span.name, assertion_name=assertion_name, passed=True,
                    ))

        passed = sum(1 for r in results if r.passed)
        failed = sum(1 for r in results if not r.passed)

        return AssertionReplayResult(
            trace_id=trace.trace_id,
            total_assertions=len(results),
            passed=passed,
            failed=failed,
            results=results,
        )


def mutate_trace(trace: ExecutionTrace, mutation: str = "random_failure") -> ExecutionTrace:
    """Create a mutated copy of a trace for mutation testing.

    Mutations:
    - "random_failure": Fail a random completed span
    - "slow_down": Double all durations
    - "drop_context": Remove output_data from agents
    """
    import copy
    import random

    mutated = copy.deepcopy(trace)

    if mutation == "random_failure":
        completed = [s for s in mutated.spans if s.status == SpanStatus.COMPLETED]
        if completed:
            target = random.choice(completed)
            target.status = SpanStatus.FAILED
            target.error = f"Mutated failure in {target.name}"

    elif mutation == "slow_down":
        from datetime import datetime
        for s in mutated.spans:
            if s.ended_at and s.started_at:
                try:
                    start = datetime.fromisoformat(s.started_at)
                    end = datetime.fromisoformat(s.ended_at)
                    new_end = start + (end - start) * 2
                    s.ended_at = new_end.isoformat()
                except Exception:
                    pass

    elif mutation == "drop_context":
        for s in mutated.spans:
            if s.span_type == SpanType.AGENT:
                s.output_data = None

    return mutated


def replay_golden(
    golden_path: str,
    current_trace: ExecutionTrace,
    tolerance_ms: float = 500.0,
    score_threshold: float = 0.0,
) -> AssertionReplayResult:
    """Compare a current trace against a golden (known-good) baseline.

    Loads the golden trace from disk and asserts that the current trace
    preserves key properties: same agent set, no new failures, durations
    within tolerance, and score not regressed.

    This is the main entry point for CI/regression testing — save a golden
    trace once, then assert every new run matches it.

    Args:
        golden_path: Path to the golden trace JSON file.
        current_trace: The trace from the current run to verify.
        tolerance_ms: Maximum allowed duration increase per span (ms).
        score_threshold: Minimum acceptable score delta vs golden.
            Negative means current can score lower by this much.

    Returns:
        ReplayResult with pass/fail for each structural assertion.

    Raises:
        FileNotFoundError: If golden_path does not exist.
        ValueError: If golden file contains invalid JSON or trace data.
    """
    import json
    from pathlib import Path

    gp = Path(golden_path)
    if not gp.exists():
        raise FileNotFoundError(f"Golden trace not found: {golden_path}")

    try:
        data = json.loads(gp.read_text(encoding="utf-8"))
        golden = ExecutionTrace.from_dict(data)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in golden trace: {e}") from e
    except (KeyError, TypeError) as e:
        raise ValueError(f"Invalid trace format in golden trace: {e}") from e

    return compare_golden(golden, current_trace, tolerance_ms, score_threshold)


def _assert_agents_present(
    golden_agents: dict, current_agents: dict,
) -> list[AssertionResult]:
    """Assert all golden agents exist in current trace."""
    return [AssertionResult(
        span_name=name, assertion_name="agent_present",
        passed=name in current_agents,
        message="" if name in current_agents else f"Agent '{name}' missing from current trace",
    ) for name in golden_agents]


def _assert_no_status_regression(
    golden_agents: dict, current_agents: dict,
) -> list[AssertionResult]:
    """Assert completed golden agents haven't regressed to failed."""
    results = []
    for name, gs in golden_agents.items():
        cs = current_agents.get(name)
        if not cs:
            continue
        regressed = gs.status == SpanStatus.COMPLETED and cs.status == SpanStatus.FAILED
        results.append(AssertionResult(
            span_name=name, assertion_name="no_status_regression",
            passed=not regressed,
            message=f"Agent '{name}' regressed: completed → failed ({cs.error or ''})" if regressed else "",
        ))
    return results


def _assert_duration_tolerance(
    golden_agents: dict, current_agents: dict, tolerance_ms: float,
) -> list[AssertionResult]:
    """Assert agent durations are within tolerance of golden baseline."""
    results = []
    for name, gs in golden_agents.items():
        cs = current_agents.get(name)
        if not cs or gs.duration_ms is None or cs.duration_ms is None:
            continue
        delta = cs.duration_ms - gs.duration_ms
        within = delta <= tolerance_ms
        results.append(AssertionResult(
            span_name=name,
            assertion_name=f"duration_tolerance({tolerance_ms}ms)",
            passed=within,
            message="" if within else (
                f"Agent '{name}' slower by {delta:.0f}ms "
                f"(golden: {gs.duration_ms:.0f}ms, current: {cs.duration_ms:.0f}ms)"
            ),
        ))
    return results


def _assert_score_not_regressed(
    golden: ExecutionTrace, current: ExecutionTrace, threshold: float,
) -> AssertionResult:
    """Assert overall score hasn't regressed beyond threshold."""
    gs = score_trace(golden)
    cs = score_trace(current)
    delta = cs.overall - gs.overall
    ok = delta >= threshold
    return AssertionResult(
        span_name="(trace)",
        assertion_name=f"score_not_regressed(threshold={threshold})",
        passed=ok,
        message="" if ok else (
            f"Score regressed: {gs.overall:.0f} → {cs.overall:.0f} "
            f"(delta: {delta:+.0f}, threshold: {threshold:+.0f})"
        ),
    )


def compare_golden(
    golden: ExecutionTrace,
    current: ExecutionTrace,
    tolerance_ms: float = 500.0,
    score_threshold: float = 0.0,
) -> AssertionReplayResult:
    """Compare current trace against a golden baseline.

    Checks: agent presence, status regression, duration tolerance, score.
    """
    golden_agents = {s.name: s for s in golden.agent_spans}
    current_agents = {s.name: s for s in current.agent_spans}

    results = (
        _assert_agents_present(golden_agents, current_agents)
        + _assert_no_status_regression(golden_agents, current_agents)
        + _assert_duration_tolerance(golden_agents, current_agents, tolerance_ms)
        + [_assert_score_not_regressed(golden, current, score_threshold)]
    )
    passed = sum(1 for r in results if r.passed)
    return AssertionReplayResult(
        trace_id=current.trace_id, total_assertions=len(results),
        passed=passed, failed=len(results) - passed, results=results,
    )

