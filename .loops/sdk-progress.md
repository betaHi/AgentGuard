# SDK Loop Progress

## Status: Sprint 1 Complete ✅

### Completed
- [x] ExecutionTrace schema (trace.py)
- [x] Span schema with parent-child nesting
- [x] @record_agent decorator
- [x] @record_tool decorator
- [x] TraceRecorder with thread-safe context stack
- [x] JSON serialization/deserialization
- [x] Tree assembly (build_tree)
- [x] Tests: 11/11 passing

### Next (Sprint 2)
- [ ] AgentConfig schema (config.py) — version management
- [ ] Async decorator variants (@record_agent_async)
- [ ] Context propagation for multi-process agents
- [ ] OTel-compatible export format

### Design Decisions (DO NOT CHANGE)
- Spans stored as flat list with parent_span_id linkage
- trace_id = uuid4()[:16], span_id = uuid4()[:12]
- Zero external deps in core/ and sdk/
- TraceRecorder uses threading.local() for span stack
