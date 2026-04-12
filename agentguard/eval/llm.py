"""LLM-based evaluation — pairwise comparison of agent outputs.

Uses any OpenAI-compatible API for evaluation. Requires AGENTGUARD_LLM_API_KEY
and optionally AGENTGUARD_LLM_BASE_URL environment variables.

This module is optional — core evaluation works fine with rules alone.

Usage:
    from agentguard.eval.llm import LLMEvaluator
    
    evaluator = LLMEvaluator(model="gpt-4o-mini"  # uses AGENTGUARD_LLM_API_KEY env var)
    result = evaluator.pairwise_compare(
        baseline_output="...",
        candidate_output="...",
        criteria="Which output is more comprehensive and accurate?"
    )
"""

from __future__ import annotations

import json
import os
import urllib.request
import urllib.error
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class LLMEvalResult:
    """Result of an LLM evaluation."""
    winner: str  # "baseline", "candidate", or "tie"
    score: float  # -1 to 1 (negative = baseline better, positive = candidate better)
    explanation: str
    model: str
    raw_response: Optional[str] = None


class LLMEvaluator:
    """Evaluate agent outputs using an LLM judge.
    
    Supports any OpenAI-compatible API (OpenAI, Anthropic via proxy, local models, etc.)
    
    Args:
        api_key: API key. Falls back to AGENTGUARD_LLM_API_KEY env var.
        base_url: API base URL. Falls back to AGENTGUARD_LLM_BASE_URL or OpenAI default.
        model: Model name for evaluation.
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = "gpt-4o-mini",
    ):
        self.api_key = api_key or os.environ.get("AGENTGUARD_LLM_API_KEY", "")
        self.base_url = (base_url or os.environ.get("AGENTGUARD_LLM_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        self.model = model
    
    def pairwise_compare(
        self,
        baseline_output: Any,
        candidate_output: Any,
        criteria: str = "Which output is better overall? Consider completeness, accuracy, and quality.",
        context: str = "",
    ) -> LLMEvalResult:
        """Compare two outputs and determine which is better.
        
        Args:
            baseline_output: Output from the baseline version.
            candidate_output: Output from the candidate version.
            criteria: What to evaluate on.
            context: Additional context about the task.
        
        Returns:
            LLMEvalResult with winner, score, and explanation.
        """
        prompt = f"""You are evaluating two AI agent outputs. Compare them based on the given criteria.

{f"Context: {context}" if context else ""}

Criteria: {criteria}

--- Output A (Baseline) ---
{json.dumps(baseline_output, indent=2, ensure_ascii=False) if not isinstance(baseline_output, str) else baseline_output}

--- Output B (Candidate) ---
{json.dumps(candidate_output, indent=2, ensure_ascii=False) if not isinstance(candidate_output, str) else candidate_output}

Respond in this exact JSON format:
{{
  "winner": "A" or "B" or "tie",
  "score": <float from -1 to 1, where -1 means A is much better, 1 means B is much better>,
  "explanation": "<brief explanation>"
}}"""

        try:
            response_text = self._call_api(prompt)
            # Parse JSON from response
            # Handle potential markdown wrapping
            text = response_text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            
            data = json.loads(text)
            winner_map = {"A": "baseline", "B": "candidate", "tie": "tie"}
            
            return LLMEvalResult(
                winner=winner_map.get(data.get("winner", "tie"), "tie"),
                score=float(data.get("score", 0)),
                explanation=data.get("explanation", ""),
                model=self.model,
                raw_response=response_text,
            )
        except Exception as e:
            return LLMEvalResult(
                winner="tie",
                score=0,
                explanation=f"LLM evaluation failed: {e}",
                model=self.model,
            )
    
    def _call_api(self, prompt: str) -> str:
        """Call the LLM API using urllib (no external deps)."""
        if not self.api_key:
            raise ValueError(
                "No API key provided. Set AGENTGUARD_LLM_API_KEY environment variable "
                "or pass api_key to LLMEvaluator."
            )
        
        payload = json.dumps({
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
        }).encode("utf-8")
        
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )
        
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]
