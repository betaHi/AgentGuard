# AgentGuard — Sprint 5: Bug Fixes & Quality

## Current Stories

### P0: Cost/Token data not flowing to analysis
- [x] Fix: multi_model_pipeline.py — agent output has cost_usd/tokens but span.estimated_cost_usd is None → cost-yield analysis shows "free" for all agents. Root cause: record_agent/record_tool decorators don't extract cost_usd/token_count from output_data into span fields. Fix: either (a) auto-extract known keys from output_data, or (b) update examples to explicitly set span cost via SDK API. Preferred: option (a) — if output_data contains "cost_usd" or "tokens_used"/"token_count", copy to span fields automatically
- [x] Fix: coding_pipeline.py — same issue, total_cost shows $0.0766 in output but analyze_cost shows $0.00
- [x] Test: verify cost-yield analysis returns non-zero costs when agents report cost in output_data

### P1: Context Flow false positives in parallel pipelines
- [x] Fix: parallel_pipeline.py context flow reports truncation between parallel agents (web_researcher → academic_researcher: -85%) — these are independent parallel agents, NOT a handoff chain. Context flow should only analyze actual handoff pairs, not sequential siblings
- [x] Test: parallel pipeline context flow should NOT report truncation between independent parallel agents

### P2: deep_analysis_demo duration is 0ms
- [ ] Fix: deep_analysis_demo.py — TraceBuilder-constructed spans have 0ms duration because timestamps aren't set. TraceBuilder.add_agent/add_tool should accept duration_ms parameter and auto-set started_at/ended_at
- [ ] Test: TraceBuilder with duration_ms produces spans with correct timestamps

### P3: Correlation analysis always empty on single trace
- [ ] Fix: correlation analysis returns 0 correlations on single trace — it should still detect patterns within a single trace (e.g., failed spans sharing same parent, timing clusters). If single-trace correlation is inherently limited, document this clearly and show a multi-trace example
- [ ] Test: correlation analysis on a complex single trace returns at least basic patterns

### P4: Screenshot generation script
- [ ] Create scripts/generate_screenshots.py — Playwright script to regenerate all 8 README screenshots from live HTML report + CLI output. Should be runnable with `python scripts/generate_screenshots.py`. Document in CONTRIBUTING.md

### P5: Review all examples output quality
- [ ] Review: run ALL 20 examples, verify each produces correct non-zero metrics, no misleading output
- [ ] Fix any examples that show incorrect/misleading data
- [ ] Test: add integration test that runs all examples and checks exit code 0 + output sanity
