# Eval Loop Progress

## Status: Not Started

### Dependencies
- [x] core/trace.py — ExecutionTrace and Span schemas (available)

### Next (Sprint 2)
- [ ] Rule-based assertion engine (rules.py)
  - min_count: check minimum number of items
  - each_has: check all items have required fields
  - recency: check dates within N days
  - no_duplicates: check unique values
  - contains_keywords: check keyword presence
- [ ] EvaluationResult schema
- [ ] Test suite for all rule types
- [ ] Integration with CLI: `agentguard eval`

### Design Decisions
- Rules defined in YAML config (agentguard.yaml)
- Each rule returns: name, type, result (pass/fail), actual value, detail
- LLM evaluation deferred to Sprint 3
