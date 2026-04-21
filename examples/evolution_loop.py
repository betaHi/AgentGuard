"""End-to-end evolution learning loop example."""

from __future__ import annotations

import tempfile

from agentguard.builder import TraceBuilder
from agentguard.evolve import EvolutionEngine


def build_evolution_trace(run_id: int):
    """Build a deterministic trace with recurring orchestration issues."""
    reviewer_ms = 3600 + (run_id * 150)
    return (
        TraceBuilder("evolution loop")
        .agent("coordinator", duration_ms=6200 + (run_id * 100))
            .agent("researcher", duration_ms=1100)
                .tool("search_docs", duration_ms=500)
            .end()
            .handoff("researcher", "reviewer", context_size=1800)
            .agent("reviewer", duration_ms=reviewer_ms)
                .tool("llm_review", duration_ms=3200)
            .end()
            .agent("notifier", duration_ms=450, status="failed", error="webhook timeout")
            .end()
        .end()
        .build()
    )


def run_evolution_demo(knowledge_dir: str) -> dict:
    """Run multiple learning cycles and return structured results."""
    engine = EvolutionEngine(knowledge_dir=knowledge_dir)
    reflections = []

    for run_id in range(1, 4):
        trace = build_evolution_trace(run_id)
        reflection = engine.learn(trace)
        comparison = engine.compare_to_best(trace)
        reflections.append({
            "trace_id": trace.trace_id,
            "lesson_count": len(reflection.lessons),
            "trend": comparison["trend"],
        })

    suggestions = engine.suggest(min_confidence=0.6)
    trends = engine.detect_trends()
    prd = engine.generate_prd(min_occurrences=2)
    return {
        "reflections": reflections,
        "trace_count": engine.kb.trace_count,
        "suggestion_count": len(suggestions),
        "trend_count": len(trends),
        "top_suggestion": suggestions[0].suggestion if suggestions else "",
        "top_trend": trends[0]["type"] if trends else "",
        "prd": prd,
    }


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="agentguard-evolution-") as tmpdir:
        result = run_evolution_demo(tmpdir)
        print("AgentGuard Evolution Loop")
        print(f"Traces learned: {result['trace_count']}")
        print(f"Suggestions: {result['suggestion_count']}")
        print(f"Trends: {result['trend_count']}")
        print(f"Top suggestion: {result['top_suggestion']}")
        print(f"Top trend: {result['top_trend']}")
        print(result["prd"].splitlines()[0])


if __name__ == "__main__":
    main()