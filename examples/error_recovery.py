"""Example: Error Recovery Patterns.

Demonstrates how AgentGuard captures different failure handling patterns:
1. Retry with backoff — tool retries 3 times before succeeding
2. Circuit breaker — agent catches tool failure and falls back
3. Graceful degradation — pipeline continues despite partial failure
4. Failure propagation — unhandled failure bubbles up
"""

import time
import random
import sys
import os

random.seed(42)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agentguard import record_agent, record_tool, record_handoff
from agentguard.sdk.recorder import init_recorder, finish_recording
from agentguard.propagation import analyze_propagation
from agentguard.scoring import score_trace
from agentguard.ascii_viz import gantt_chart


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


def main():
    print("🛡️ Error Recovery Patterns Demo")
    print("=" * 50)
    
    recorder = init_recorder(task="Error Recovery Patterns")
    
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
        result4 = critical_agent()
    except RuntimeError as e:
        print(f"   Caught: {e}")
    
    trace = finish_recording()
    
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
