"""Example: Multi-Agent Coding Pipeline.

A realistic scenario: user requests a feature, multiple specialized agents
collaborate to plan, implement, review, test, and deploy it.

This is the kind of pipeline behind tools like Cursor, Copilot Workspace,
and Claude Code — and exactly what AgentGuard is built to observe.

Pipeline:
  coordinator
  ├── planner          — breaks task into subtasks, writes spec
  ├── code-searcher    — finds relevant existing code
  ├── code-generator   — writes implementation
  ├── code-reviewer    — reviews for quality, security, style
  ├── test-runner      — runs tests, checks coverage
  ├── (fix loop)       — if review/tests fail, generator retries
  └── deployer         — creates PR, triggers CI
"""

import time
import random

# Seed for reproducible demo output
random.seed(42)
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agentguard import record_agent, record_tool, record_handoff
from agentguard.sdk.recorder import init_recorder, finish_recording
from agentguard.analysis import analyze_failures, analyze_flow, analyze_bottleneck
from agentguard.web.viewer import generate_timeline_html


# ──────────────────────────────────────────
# Tools
# ──────────────────────────────────────────

@record_tool(name="llm_plan")
def llm_plan(task_description: str) -> dict:
    """LLM generates an implementation plan."""
    time.sleep(random.uniform(0.3, 0.5))
    return {
        "subtasks": [
            "Add REST endpoint /api/agents/{id}/traces",
            "Implement pagination with cursor-based approach",
            "Add input validation and error handling",
            "Write unit tests for the new endpoint",
        ],
        "estimated_files": 3,
        "complexity": "medium",
    }

@record_tool(name="codebase_search")
def codebase_search(query: str) -> list[dict]:
    """Search existing codebase for relevant code."""
    time.sleep(random.uniform(0.1, 0.2))
    return [
        {"file": "src/api/routes.py", "relevance": 0.95, "snippet": "class TracesRouter..."},
        {"file": "src/models/trace.py", "relevance": 0.88, "snippet": "class Trace(BaseModel)..."},
        {"file": "tests/test_api.py", "relevance": 0.72, "snippet": "def test_list_traces()..."},
    ]

@record_tool(name="vector_search")
def vector_search(query: str) -> list[dict]:
    """Vector similarity search over code embeddings."""
    time.sleep(random.uniform(0.05, 0.1))
    # Simulating intermittent failure
    if random.random() < 0.6:
        raise ConnectionError("Embedding service timeout: Pinecone cluster unresponsive")
    return [{"file": "src/utils/pagination.py", "score": 0.91}]

@record_tool(name="keyword_search_fallback")
def keyword_search(query: str) -> list[dict]:
    """Fallback: simple keyword search when vector search fails."""
    time.sleep(0.03)
    return [{"file": "src/utils/pagination.py", "score": 0.65, "method": "keyword"}]

@record_tool(name="llm_generate_code")
def llm_generate_code(spec: dict, context: list) -> dict:
    """LLM generates implementation code."""
    time.sleep(random.uniform(0.5, 0.8))  # This is the slow part
    return {
        "files_modified": [
            {"path": "src/api/traces.py", "action": "create", "lines": 87},
            {"path": "src/api/routes.py", "action": "modify", "lines": 12},
            {"path": "src/models/trace.py", "action": "modify", "lines": 5},
        ],
        "tokens_used": random.randint(2000, 4000),
    }

@record_tool(name="llm_review_code")
def llm_review_code(code_diff: dict) -> dict:
    """LLM reviews code for quality issues."""
    time.sleep(random.uniform(0.3, 0.5))
    issues = []
    if random.random() < 0.05:
        issues.append({"severity": "warning", "file": "src/api/traces.py", "line": 42,
                       "message": "Missing rate limiting on public endpoint"})
    if random.random() < 0.02:
        issues.append({"severity": "error", "file": "src/api/traces.py", "line": 15,
                       "message": "SQL injection vulnerability in query parameter"})
    return {
        "approved": len([i for i in issues if i["severity"] == "error"]) == 0,
        "issues": issues,
        "score": 0.85 if not issues else 0.6,
    }

@record_tool(name="run_tests")
def run_tests(files: list) -> dict:
    """Execute test suite."""
    time.sleep(random.uniform(0.2, 0.4))
    passed = random.randint(18, 24)
    failed = 0
    return {
        "passed": passed, "failed": failed, "total": passed + failed,
        "coverage": round(random.uniform(0.75, 0.92), 2),
        "duration_s": round(random.uniform(3.0, 8.0), 1),
    }

@record_tool(name="static_analysis")
def static_analysis(files: list) -> dict:
    """Run linting and type checking."""
    time.sleep(random.uniform(0.1, 0.15))
    return {"lint_errors": 0, "type_errors": 0, "tool": "ruff + mypy"}

@record_tool(name="create_pull_request")
def create_pr(title: str, files: list) -> dict:
    """Create a GitHub pull request."""
    time.sleep(random.uniform(0.1, 0.2))
    return {"pr_number": 42, "url": "https://github.com/org/repo/pull/42", "status": "open"}

@record_tool(name="trigger_ci")
def trigger_ci(pr_number: int) -> dict:
    """Trigger CI pipeline."""
    time.sleep(0.05)
    return {"run_id": 12345, "status": "queued"}

@record_tool(name="send_slack_notification")
def send_slack(channel: str, message: str) -> dict:
    """Send Slack notification."""
    time.sleep(0.02)
    if True:  # always fail notification
        raise ConnectionError("Slack API rate limited (429)")
    return {"sent": True}


# ──────────────────────────────────────────
# Agents
# ──────────────────────────────────────────

@record_agent(name="planner", version="v2.1")
def planner(user_request: str) -> dict:
    """Breaks down user request into an implementation plan."""
    plan = llm_plan(user_request)
    return {
        "plan": plan,
        "user_request": user_request,
        "subtask_count": len(plan["subtasks"]),
    }

@record_agent(name="code-searcher", version="v1.4")
def code_searcher(plan: dict) -> dict:
    """Finds relevant code in the codebase."""
    # Primary: vector search (may fail)
    try:
        vector_results = vector_search(plan["plan"]["subtasks"][0])
    except Exception:
        # Fallback to keyword search
        vector_results = keyword_search(plan["plan"]["subtasks"][0])
    
    # Always do codebase search
    code_results = codebase_search(plan["plan"]["subtasks"][0])
    
    return {
        "relevant_files": code_results,
        "similar_code": vector_results,
        "total_context_files": len(code_results) + len(vector_results),
    }

@record_agent(name="code-generator", version="v3.0")
def code_generator(spec: dict, context: dict) -> dict:
    """Generates implementation code."""
    code = llm_generate_code(spec, context.get("relevant_files", []))
    return {
        "code": code,
        "files_modified": len(code["files_modified"]),
        "total_lines": sum(f["lines"] for f in code["files_modified"]),
    }

@record_agent(name="code-reviewer", version="v2.3")
def code_reviewer(code: dict) -> dict:
    """Reviews generated code for quality and security."""
    review = llm_review_code(code)
    lint = static_analysis(code.get("code", {}).get("files_modified", []))
    return {
        "review": review,
        "lint": lint,
        "approved": review["approved"] and lint["lint_errors"] == 0,
    }

@record_agent(name="test-runner", version="v1.2")
def test_runner(code: dict) -> dict:
    """Runs tests against the generated code."""
    results = run_tests(code.get("code", {}).get("files_modified", []))
    return {
        "test_results": results,
        "all_passed": results["failed"] == 0,
        "coverage": results["coverage"],
    }

@record_agent(name="deployer", version="v1.5")
def deployer(code: dict, test_results: dict) -> dict:
    """Creates PR and triggers CI."""
    pr = create_pr(
        title=f"feat: Add agent traces endpoint ({code['total_lines']} lines)",
        files=code.get("code", {}).get("files_modified", []),
    )
    ci = trigger_ci(pr["pr_number"])
    return {"pr": pr, "ci": ci}

@record_agent(name="notifier", version="v1.0")
def notifier(deployment: dict) -> dict:
    """Sends notifications about the deployment."""
    results = {}
    results["team"] = send_slack("#engineering", f"PR #{deployment['pr']['pr_number']} created")
    try:
        results["alerts"] = send_slack("deploy-alerts", "New deployment queued")
    except Exception as e:
        raise RuntimeError(f"Critical notification channel failed: {e}")
    return results


@record_agent(name="coding-pipeline", version="v4.0")
def coding_pipeline(user_request: str) -> dict:
    """Full coding pipeline coordinator."""
    
    # Phase 1: Plan
    plan = planner(user_request)
    record_handoff("planner", "code-searcher", context=plan,
                   summary=f"Implementation plan with {plan['subtask_count']} subtasks")
    
    # Phase 2: Search context
    context = code_searcher(plan)
    record_handoff("code-searcher", "code-generator", context=context,
                   summary=f"Found {context['total_context_files']} relevant files")
    
    # Phase 3: Generate code
    code = code_generator(plan, context)
    record_handoff("code-generator", "code-reviewer", context=code,
                   summary=f"Generated {code['total_lines']} lines across {code['files_modified']} files")
    
    # Phase 4: Review
    review = code_reviewer(code)
    
    # Phase 5: Test
    record_handoff("code-reviewer", "test-runner", context=review,
                   summary=f"Review {'approved' if review['approved'] else 'needs fixes'}")
    tests = test_runner(code)
    
    # Phase 6: Deploy (only if review passed and tests passed)
    if review["approved"] and tests["all_passed"]:
        record_handoff("test-runner", "deployer", context=tests,
                       summary=f"All {tests['test_results']['total']} tests passed, {tests['coverage']:.0%} coverage")
        deployment = deployer(code, tests)
        
        # Phase 7: Notify (may fail)
        try:
            record_handoff("deployer", "notifier", context=deployment,
                           summary=f"PR #{deployment['pr']['pr_number']} ready for notification")
            notifier(deployment)
        except Exception:
            pass  # Pipeline continues even if notification fails
        
        return {
            "status": "deployed",
            "pr": deployment["pr"]["url"],
            "tests": f"{tests['test_results']['passed']}/{tests['test_results']['total']} passed",
            "coverage": f"{tests['coverage']:.0%}",
        }
    else:
        return {
            "status": "needs_fixes",
            "review_approved": review["approved"],
            "tests_passed": tests["all_passed"],
        }


# ──────────────────────────────────────────
# Main
# ──────────────────────────────────────────

def main():
    print("=" * 70)
    print("  AgentGuard Example: Multi-Agent Coding Pipeline")
    print("=" * 70)
    
    init_recorder(
        task="feat: Add /api/agents/{id}/traces endpoint",
        trigger="pull_request",
    )
    
    result = coding_pipeline(
        "Add a new REST API endpoint that returns paginated trace data "
        "for a specific agent, including filtering by date range and status."
    )
    
    trace = finish_recording()
    
    print(f"\n{'─' * 70}")
    print(f"  Result: {result['status']}")
    if result["status"] == "deployed":
        print(f"  PR: {result['pr']}")
        print(f"  Tests: {result['tests']}")
        print(f"  Coverage: {result['coverage']}")
    print(f"{'─' * 70}")
    print(f"  Trace: {trace.trace_id}")
    print(f"  Spans: {len(trace.spans)} ({len(trace.agent_spans)} agents, {len(trace.tool_spans)} tools)")
    print(f"  Handoffs: {sum(1 for s in trace.spans if s.span_type.value == 'handoff')}")
    print(f"  Duration: {trace.duration_ms:.0f}ms")
    
    # Analysis
    failures = analyze_failures(trace)
    bottleneck = analyze_bottleneck(trace)
    flow = analyze_flow(trace)
    
    print(f"\n  Resilience: {failures.resilience_score:.0%}")
    print(f"  Bottleneck: {bottleneck.bottleneck_span} ({bottleneck.bottleneck_pct:.0f}%)")
    print(f"  Handoffs: {len(flow.handoffs)}")
    for h in flow.handoffs:
        print(f"    🔀 {h.from_agent} → {h.to_agent} ({h.context_size_bytes}B)")
    
    # Generate report
    report = generate_timeline_html()
    print(f"\n  📊 CLI: agentguard show .agentguard/traces/{trace.trace_id}.json")
    print(f"  📊 CLI: agentguard analyze .agentguard/traces/{trace.trace_id}.json")
    print(f"  🌐 Web: {report}")
    # Self-reflection and learning
    from agentguard.evolve import EvolutionEngine
    engine = EvolutionEngine()
    reflection = engine.learn(trace)
    
    print(f"\n  🧠 Self-Reflection:")
    for l in reflection.lessons[:3]:
        icon = {"failure": "🔴", "bottleneck": "🐢", "handoff": "🔀"}.get(l.category, "•")
        print(f"    {icon} {l.agent}: {l.suggestion[:60]}")
    
    suggestions = engine.suggest()
    if suggestions:
        print(f"\n  💡 Top Suggestion (from {engine.kb.trace_count} runs):")
        s = suggestions[0]
        print(f"    {s.agent}: {s.suggestion} ({s.confidence:.0%} confidence)")
    
    print(f"{'═' * 70}")


if __name__ == "__main__":
    main()
