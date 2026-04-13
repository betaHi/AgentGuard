"""Debugging a real failure: agent B fails because agent A dropped "user_id".

Demonstrates Q2 analysis — identifying which handoff lost critical context.
The trace shows:
  1. coordinator delegates to agent_a (auth service)
  2. agent_a outputs auth_token AND user_id
  3. But agent_b only receives auth_token — user_id lost in transit
  4. agent_b fails with KeyError because "user_id" is missing

Running this example prints the context flow analysis pinpointing the lost key
and the failure analysis linking agent_b's error to the dropped context.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agentguard.builder import TraceBuilder
from agentguard.analysis import analyze_context_flow, analyze_failures


def build_context_loss_trace():
    """Build a trace where user_id is lost between agent_a and agent_b.

    agent_a correctly outputs user_id, but the orchestrator's handoff
    drops it — agent_b only receives auth_token, causing a KeyError.
    """
    trace = (TraceBuilder("user profile lookup")
        .agent("coordinator", duration_ms=5000,
               input_data={"user_id": "u-123", "request_type": "profile"})
            .agent("agent_a", duration_ms=2000,
                   input_data={"user_id": "u-123"},
                   output_data={"auth_token": "tok-abc",
                                "user_id": "u-123"})
                .tool("validate_token", duration_ms=500)
            .end()
            # user_id lost during handoff:
            .agent("agent_b", duration_ms=100,
                   input_data={"auth_token": "tok-abc"},  # user_id missing!
                   status="failed",
                   error="KeyError: 'user_id' — required for profile lookup")
            .end()
        .end()
        .build())
    return trace


def analyze_and_print(trace):
    """Run Q2 context flow analysis and print findings."""
    ctx = analyze_context_flow(trace)
    failures = analyze_failures(trace)

    print("=" * 60)
    print("CONTEXT FLOW ANALYSIS (Q2: lost handoff context)")
    print("=" * 60)
    _print_context_summary(ctx)
    _print_failure_summary(failures)
    _print_diagnosis(ctx, failures)
    print("=" * 60)


def _print_context_summary(ctx):
    """Print context flow findings from ContextFlowReport."""
    print(f"\nHandoffs: {ctx.handoff_count}")
    print(f"Anomalies: {len(ctx.anomalies)}")
    for point in ctx.points:
        icon = "🟢" if point.anomaly == "ok" else "🔴"
        print(f"\n  {icon} {point.from_agent} → {point.to_agent}")
        if point.keys_lost:
            print(f"     ⚠️  Lost keys: {point.keys_lost}")
        print(f"     Sent: {point.keys_sent}")
        print(f"     Received: {point.keys_received}")


def _print_failure_summary(failures):
    """Print failure root causes from FailureAnalysis."""
    print(f"\n🔴 Failed spans: {failures.total_failed_spans}")
    for rc in failures.root_causes:
        print(f"   • {rc.span_name}: {rc.error}")


def _print_diagnosis(ctx, failures):
    """Correlate context loss with failure."""
    lost_keys = []
    for p in ctx.points:
        lost_keys.extend(p.keys_lost)
    if lost_keys and failures.total_failed_spans > 0:
        print(f"\n💡 DIAGNOSIS: Keys {lost_keys} were dropped during handoff.")
        print(f"   This directly caused {failures.total_failed_spans} failure(s).")
        print("   Fix: ensure orchestrator forwards all required keys.")


if __name__ == "__main__":
    trace = build_context_loss_trace()
    analyze_and_print(trace)
