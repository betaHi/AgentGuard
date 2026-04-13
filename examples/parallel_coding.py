"""Example: Parallel Coding Pipeline with concurrent review + testing.

  coordinator
  ├── planner                     — creates implementation plan
  ├── code-generator              — writes code
  ├── [PARALLEL] code-reviewer    — reviews code quality
  ├── [PARALLEL] security-scanner — scans for vulnerabilities
  ├── [PARALLEL] test-runner      — runs test suite
  │
  ├── [SEQUENTIAL] fixer          — fixes issues from all 3
  └── [SEQUENTIAL] deployer       — creates PR

The review, security scan, and tests run in PARALLEL after code generation.
"""

import os
import random
import sys
import time

random.seed(42)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agentguard import TraceThread, mark_context_used, record_agent, record_handoff, record_tool
from agentguard.ascii_viz import gantt_chart, status_summary
from agentguard.scoring import score_trace
from agentguard.sdk.recorder import finish_recording, init_recorder
from agentguard.store import TraceStore
from agentguard.web.viewer import generate_timeline_html


@record_tool(name="llm_plan")
def llm_plan(task):
    time.sleep(random.uniform(0.3, 0.5))
    return {"subtasks": ["endpoint", "validation", "tests"], "files": ["api.py", "tests.py"]}

@record_tool(name="llm_generate")
def llm_generate(plan):
    time.sleep(random.uniform(0.5, 0.8))
    return {"code": "def endpoint(): ...", "files_changed": 2}

@record_tool(name="llm_review")
def llm_review(code):
    time.sleep(random.uniform(0.3, 0.5))
    return {"issues": ["naming: use snake_case"], "severity": "low", "approved": True}

@record_tool(name="semgrep_scan")
def semgrep_scan(code):
    time.sleep(random.uniform(0.2, 0.4))
    return {"vulnerabilities": 0, "warnings": 1, "clean": True}

@record_tool(name="pytest_run")
def pytest_run(code):
    time.sleep(random.uniform(0.4, 0.7))
    if random.random() < 0.3:
        raise AssertionError("test_auth_flow failed")
    return {"passed": 15, "failed": 0, "coverage": 0.87}

@record_tool(name="git_pr")
def git_pr(changes):
    time.sleep(random.uniform(0.1, 0.2))
    return {"pr_number": 42, "url": "https://github.com/org/repo/pull/42"}


@record_agent(name="planner", version="v1.0")
def plan(task):
    return llm_plan(task)

@record_agent(name="code-generator", version="v2.1")
def generate(plan):
    return llm_generate(plan)

@record_agent(name="code-reviewer", version="v1.0")
def review(code):
    return llm_review(code)

@record_agent(name="security-scanner", version="v1.0")
def security_scan(code):
    return semgrep_scan(code)

@record_agent(name="test-runner", version="v1.0")
def run_tests(code):
    try:
        return pytest_run(code)
    except AssertionError as e:
        return {"passed": 14, "failed": 1, "error": str(e)}

@record_agent(name="fixer", version="v1.0")
def fix_issues(review_result, security_result, test_result):
    time.sleep(random.uniform(0.2, 0.3))
    return {"fixed": True, "changes": 1}

@record_agent(name="deployer", version="v1.0")
def deploy(changes):
    return git_pr(changes)


@record_agent(name="parallel-coding-coordinator", version="v1.0")
def orchestrate_parallel_coding(task: str) -> dict:
    """Coordinate the full parallel coding workflow under one root span."""
    # Phase 1: Plan
    plan_result = plan(task)
    record_handoff("planner", "code-generator", context=plan_result, summary="Implementation plan")

    # Phase 2: Generate code
    code_result = generate(plan_result)

    # Phase 3: PARALLEL — review + security + tests
    results = {}

    def run_parallel(name, fn, *args):
        results[name] = fn(*args)

    print("⚡ Running review, security scan, and tests in parallel...")
    threads = [
        TraceThread(target=run_parallel, args=("review", review, code_result)),
        TraceThread(target=run_parallel, args=("security", security_scan, code_result)),
        TraceThread(target=run_parallel, args=("tests", run_tests, code_result)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    review_result = results["review"]
    security_result = results["security"]
    test_result = results["tests"]

    # Handoffs from all 3 → fixer
    for src, data in [("code-reviewer", review_result), ("security-scanner", security_result), ("test-runner", test_result)]:
        h = record_handoff(src, "fixer", context=data, summary=f"Results from {src}")
        mark_context_used(h, used_keys=list(data.keys()) if isinstance(data, dict) else [])

    # Phase 4: Fix
    fixed = fix_issues(review_result, security_result, test_result)
    record_handoff("fixer", "deployer", context=fixed)

    # Phase 5: Deploy
    pr = deploy(fixed)
    return {"pr": pr, "fixed": fixed}


def main():
    print("🖥️ Parallel Coding Pipeline")
    print("=" * 50)

    init_recorder(task="Implement /api/agents/{id}/traces endpoint")
    orchestrate_parallel_coding("Add traces endpoint with pagination")

    trace = finish_recording()

    # Analysis
    score = score_trace(trace)
    print(f"\n{status_summary(trace)}")
    print(f"\n{gantt_chart(trace)}")
    print(f"\n🎯 Score: {score.overall:.0f}/100 ({score.grade})")

    # Save + HTML
    store = TraceStore()
    store.save(trace)
    html = generate_timeline_html()
    print(f"🌐 Report: {html}")


if __name__ == "__main__":
    main()
