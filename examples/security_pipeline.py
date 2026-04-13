"""Example: Security Scanning Pipeline.

Pipeline: coordinator → scanner → analyzer → triager → remediator → verifier
"""
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
random.seed(42)

from agentguard import record_agent, record_handoff, record_tool
from agentguard.sdk.recorder import finish_recording, init_recorder


@record_tool(name="run_sast")
def run_sast(repo):
    time.sleep(0.2)
    return {"findings": [
        {"severity": "high", "file": "src/auth.py", "line": 42, "rule": "SQL-injection"},
        {"severity": "medium", "file": "src/api.py", "line": 15, "rule": "missing-rate-limit"},
        {"severity": "low", "file": "src/utils.py", "line": 88, "rule": "unused-import"},
    ]}

@record_tool(name="run_dependency_check")
def dep_check(repo):
    time.sleep(0.15)
    return {"vulnerable_deps": [{"name": "requests", "version": "2.25.0", "cve": "CVE-2026-1234"}]}

@record_tool(name="llm_analyze_finding")
def analyze_finding(finding):
    time.sleep(0.25)
    return {"exploitable": finding["severity"] == "high", "fix_suggestion": f"Fix {finding['rule']} at {finding['file']}:{finding['line']}"}

@record_tool(name="apply_fix")
def apply_fix(finding, suggestion):
    time.sleep(0.1)
    return {"fixed": True, "file": finding["file"]}

@record_tool(name="run_verify")
def verify(file):
    time.sleep(0.1)
    return {"clean": True}

@record_agent(name="scanner", version="v2.0")
def scanner(repo):
    sast = run_sast(repo)
    deps = dep_check(repo)
    return {"sast": sast, "deps": deps, "total_findings": len(sast["findings"]) + len(deps["vulnerable_deps"])}

@record_agent(name="analyzer", version="v1.5")
def analyzer(scan_results):
    analyses = []
    for f in scan_results["sast"]["findings"][:2]:
        analyses.append(analyze_finding(f))
    return {"analyses": analyses, "exploitable_count": sum(1 for a in analyses if a["exploitable"])}

@record_agent(name="remediator", version="v1.0")
def remediator(analysis):
    fixes = []
    for a in analysis["analyses"]:
        if a["exploitable"]:
            fixes.append(apply_fix({"file": "src/auth.py", "severity": "high", "rule": "SQL-injection"}, a["fix_suggestion"]))
    return {"fixes": fixes}

@record_agent(name="verifier", version="v1.0")
def verifier(fixes):
    results = []
    for f in fixes.get("fixes", []):
        results.append(verify(f["file"]))
    return {"all_clean": all(r["clean"] for r in results), "verified": len(results)}

@record_agent(name="security-coordinator", version="v3.0")
def coordinator(repo):
    scan = scanner(repo)
    record_handoff("scanner", "analyzer", context=scan, summary=f"{scan['total_findings']} findings")
    analysis = analyzer(scan)
    record_handoff("analyzer", "remediator", context=analysis, summary=f"{analysis['exploitable_count']} exploitable")
    fixes = remediator(analysis)
    record_handoff("remediator", "verifier", context=fixes, summary=f"{len(fixes['fixes'])} fixes applied")
    verification = verifier(fixes)
    return {"scan": scan, "analysis": analysis, "fixes": fixes, "verified": verification}

if __name__ == "__main__":
    init_recorder(task="Security Audit: main branch", trigger="ci_pipeline")
    result = coordinator("github.com/org/repo")
    trace = finish_recording()
    print(f"Security audit: {len(trace.spans)} spans, {trace.duration_ms:.0f}ms")
    print(f"Findings: {result['scan']['total_findings']}, Exploitable: {result['analysis']['exploitable_count']}")
