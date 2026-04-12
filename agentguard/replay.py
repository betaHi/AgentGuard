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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from agentguard.eval.rules import evaluate_rules
from agentguard.eval.compare import ComparisonResult, DiffItem
from agentguard.core.eval_schema import EvaluationResult, RuleResult, RuleVerdict

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
        rules: Optional[list[dict]] = None,
        metadata: Optional[dict] = None,
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
    
    def load_baseline(self, name: str) -> Optional[ReplayCase]:
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
        rules: Optional[list[dict]] = None,
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
        cases: Optional[list[str]] = None,
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
            except Exception as e:
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
