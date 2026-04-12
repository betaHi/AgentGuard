"""Trace replay v2 — replay traces with assertions and mutation testing.

Beyond basic baseline comparison, this module supports:
- Replaying a trace and asserting properties at each span
- Mutation testing (inject failures and see if detection works)
- Golden trace comparison (compare against a known-good trace)
- Regression detection with configurable tolerance
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from agentguard.core.trace import ExecutionTrace, Span, SpanType, SpanStatus
from agentguard.scoring import score_trace


SpanAssertion = Callable[[Span], bool]


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
class ReplayResult:
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
    
    def replay(self, trace: ExecutionTrace) -> ReplayResult:
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
            except Exception as e:
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
        
        return ReplayResult(
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
        from datetime import datetime, timezone, timedelta
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
) -> ReplayResult:
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
        raise ValueError(f"Invalid JSON in golden trace: {e}")
    except (KeyError, TypeError) as e:
        raise ValueError(f"Invalid trace format in golden trace: {e}")

    return compare_golden(golden, current_trace, tolerance_ms, score_threshold)


def compare_golden(
    golden: ExecutionTrace,
    current: ExecutionTrace,
    tolerance_ms: float = 500.0,
    score_threshold: float = 0.0,
) -> ReplayResult:
    """Compare current trace against a golden baseline (both in memory).

    Checks:
    1. All golden agents exist in current trace
    2. No golden-completed agents have regressed to failed
    3. Duration within tolerance for each agent
    4. Overall score not regressed beyond threshold

    Args:
        golden: The known-good baseline trace.
        current: The current trace to verify.
        tolerance_ms: Max allowed duration increase per agent.
        score_threshold: Min acceptable score delta (negative = allow regression).

    Returns:
        ReplayResult with detailed assertion outcomes.
    """
    results: list[AssertionResult] = []

    golden_agents = {s.name: s for s in golden.agent_spans}
    current_agents = {s.name: s for s in current.agent_spans}

    # 1. Agent presence: all golden agents must exist in current
    for name in golden_agents:
        present = name in current_agents
        results.append(AssertionResult(
            span_name=name,
            assertion_name="agent_present",
            passed=present,
            message="" if present else f"Agent '{name}' missing from current trace",
        ))

    # 2. Status regression: completed agents should not become failed
    for name, gs in golden_agents.items():
        cs = current_agents.get(name)
        if not cs:
            continue
        if gs.status == SpanStatus.COMPLETED and cs.status == SpanStatus.FAILED:
            results.append(AssertionResult(
                span_name=name,
                assertion_name="no_status_regression",
                passed=False,
                message=f"Agent '{name}' regressed: completed → failed ({cs.error or ''})",
            ))
        else:
            results.append(AssertionResult(
                span_name=name,
                assertion_name="no_status_regression",
                passed=True,
            ))

    # 3. Duration tolerance: current should not be much slower
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

    # 4. Score comparison
    golden_score = score_trace(golden)
    current_score = score_trace(current)
    score_delta = current_score.overall - golden_score.overall
    score_ok = score_delta >= score_threshold
    results.append(AssertionResult(
        span_name="(trace)",
        assertion_name=f"score_not_regressed(threshold={score_threshold})",
        passed=score_ok,
        message="" if score_ok else (
            f"Score regressed: {golden_score.overall:.0f} → {current_score.overall:.0f} "
            f"(delta: {score_delta:+.0f}, threshold: {score_threshold:+.0f})"
        ),
    ))

    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)

    return ReplayResult(
        trace_id=current.trace_id,
        total_assertions=len(results),
        passed=passed,
        failed=failed,
        results=results,
    )
