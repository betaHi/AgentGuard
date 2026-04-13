"""Example: Error Recovery Patterns.

Demonstrates how AgentGuard captures different failure handling patterns:
1. Retry with backoff — tool retries 3 times before succeeding
2. Circuit breaker — agent catches tool failure and falls back
3. Graceful degradation — pipeline continues despite partial failure
4. Failure propagation — unhandled failure bubbles up
5. Timeout with partial results — returns what it has before timeout
6. Partial result aggregation — collects from multiple sources despite failures
"""

import os
import random
import sys
import time

random.seed(42)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agentguard import record_agent, record_handoff, record_tool
from agentguard.ascii_viz import gantt_chart
from agentguard.propagation import analyze_propagation
from agentguard.scoring import score_trace
from agentguard.sdk.recorder import finish_recording, init_recorder


# ── Pattern 1: Retry with backoff ──
@record_tool(name="flaky_api")
def flaky_api(attempt: int) -> dict:
    time.sleep(0.05)
    if attempt < 3:
        raise ConnectionError(f"Attempt {attempt}: Connection refused")
    return {"data": "success after retries"}

@record_agent(name="resilient_fetcher", version="v1.0")
def resilient_fetcher() -> dict:
    """Retries up to 3 times with backoff."""
    for attempt in range(4):
        try:
            return flaky_api(attempt)
        except ConnectionError:
            if attempt < 3:
                time.sleep(0.01 * (2 ** attempt))  # exponential backoff
            else:
                raise
    return {}


# ── Pattern 2: Circuit breaker ──
@record_tool(name="premium_api")
def premium_api() -> dict:
    time.sleep(0.03)
    raise TimeoutError("Premium API is down")

@record_tool(name="free_api")
def free_api() -> dict:
    time.sleep(0.05)
    return {"data": "fallback data", "quality": "basic"}

@record_agent(name="smart_fetcher", version="v1.0")
def smart_fetcher() -> dict:
    """Falls back to free API when premium fails."""
    try:
        return premium_api()
    except TimeoutError:
        return free_api()


# ── Pattern 3: Graceful degradation ──
@record_tool(name="enrichment_api")
def enrichment_api(data: dict) -> dict:
    time.sleep(0.03)
    raise ValueError("Enrichment service unavailable")

@record_agent(name="enricher", version="v1.0")
def enricher(data: dict) -> dict:
    """Continues without enrichment if service is down."""
    try:
        return enrichment_api(data)
    except ValueError:
        return {**data, "enriched": False, "note": "Enrichment unavailable"}


# ── Pattern 4: Unhandled failure ──
@record_tool(name="critical_service")
def critical_service() -> dict:
    time.sleep(0.02)
    raise RuntimeError("Critical service crashed!")

@record_agent(name="critical_agent", version="v1.0")
def critical_agent() -> dict:
    """No error handling — failure propagates."""
    return critical_service()


# ── Pattern 5: Timeout with partial results ──
@record_tool(name="slow_search")
def slow_search(query: str, timeout_ms: float = 100) -> dict:
    """Simulates a search that may exceed timeout."""
    duration = random.uniform(0.05, 0.2)
    time.sleep(min(duration, timeout_ms / 1000))
    if duration > timeout_ms / 1000:
        raise TimeoutError(f"Search exceeded {timeout_ms}ms timeout")
    return {"results": [f"result-{i}" for i in range(3)], "query": query}

@record_agent(name="timeout_searcher", version="v1.0")
def timeout_searcher(query: str) -> dict:
    """Returns partial results on timeout instead of failing completely."""
    partial_results = []
    queries = [f"{query} part-{i}" for i in range(3)]
    for q in queries:
        try:
            result = slow_search(q, timeout_ms=100)
            partial_results.extend(result["results"])
        except TimeoutError:
            partial_results.append(f"[timeout: {q}]")
    return {
        "results": partial_results,
        "complete": not any("[timeout:" in r for r in partial_results),
        "total_queries": len(queries),
    }


# ── Pattern 6: Partial result aggregation ──
@record_tool(name="source_a")
def source_a() -> dict:
    time.sleep(0.03)
    return {"items": ["a1", "a2"], "source": "A"}

@record_tool(name="source_b")
def source_b() -> dict:
    time.sleep(0.03)
    raise ConnectionError("Source B is unreachable")

@record_tool(name="source_c")
def source_c() -> dict:
    time.sleep(0.03)
    return {"items": ["c1"], "source": "C"}

@record_agent(name="aggregator", version="v1.0")
def aggregator() -> dict:
    """Collects from multiple sources, continues despite partial failure."""
    sources = [source_a, source_b, source_c]
    collected = []
    failed_sources = []
    for src in sources:
        try:
            result = src()
            collected.extend(result["items"])
        except Exception as e:
            failed_sources.append(f"{src.__name__}: {e}")
    return {
        "items": collected,
        "total": len(collected),
        "failed_sources": failed_sources,
        "completeness": len(collected) / max(len(sources) * 2, 1),
    }


def main():
    print("🛡️ Error Recovery Patterns Demo")
    print("=" * 50)

    init_recorder(task="Error Recovery Patterns")

    # Pattern 1: Retry
    print("\n🔄 Pattern 1: Retry with backoff")
    result1 = resilient_fetcher()
    print(f"   Result: {result1}")

    record_handoff("resilient_fetcher", "smart_fetcher", context=result1)

    # Pattern 2: Circuit breaker
    print("\n🛡️ Pattern 2: Circuit breaker (fallback)")
    result2 = smart_fetcher()
    print(f"   Result: {result2}")

    record_handoff("smart_fetcher", "enricher", context=result2)

    # Pattern 3: Graceful degradation
    print("\n📉 Pattern 3: Graceful degradation")
    result3 = enricher(result2)
    print(f"   Result: {result3}")

    # Pattern 4: Unhandled failure
    print("\n💥 Pattern 4: Unhandled failure")
    try:
        critical_agent()
    except RuntimeError as e:
        print(f"   Caught: {e}")

    trace = finish_recording()

    record_handoff("enricher", "timeout_searcher", context=result3)

    # Pattern 5: Timeout with partial results
    print("\n⏱️  Pattern 5: Timeout with partial results")
    result5 = timeout_searcher("AI agents")
    print(f"   Complete: {result5['complete']}, Results: {len(result5['results'])}")

    record_handoff("timeout_searcher", "aggregator", context=result5)

    # Pattern 6: Partial result aggregation
    print("\n📦 Pattern 6: Partial result aggregation")
    result6 = aggregator()
    print(f"   Items: {result6['total']}, Failed: {len(result6['failed_sources'])}")
    for fail in result6["failed_sources"]:
        print(f"   ⚠ {fail}")

    # Analysis
    print("\n" + "=" * 50)
    print("📊 Analysis")

    score = score_trace(trace)
    print(f"\n🎯 Score: {score.overall:.0f}/100 ({score.grade})")

    prop = analyze_propagation(trace)
    print(f"\n{prop.to_report()}")

    print(f"\n{gantt_chart(trace)}")


if __name__ == "__main__":
    main()
