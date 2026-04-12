"""Trace query utilities — filter, search, and aggregate across traces.

When you have many traces on disk, these utilities help you find
patterns across executions.

Usage:
    from agentguard.query import TraceStore
    
    store = TraceStore(".agentguard/traces")
    
    # Find all traces where a specific agent failed
    failed = store.filter(agent_name="analyst", status="failed")
    
    # Get per-agent statistics
    stats = store.agent_stats()
"""



from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from agentguard.core.trace import ExecutionTrace, Span, SpanType, SpanStatus

__all__ = ['TraceStore']


class TraceStore:
    """Query interface for traces stored on disk."""
    
    def __init__(self, traces_dir: str = ".agentguard/traces"):
        self.traces_dir = Path(traces_dir)
        self._cache: Optional[list[ExecutionTrace]] = None
    
    def load_all(self) -> list[ExecutionTrace]:
        """Load all traces from disk."""
        if self._cache is not None:
            return self._cache
        
        traces = []
        if self.traces_dir.exists():
            for f in sorted(self.traces_dir.glob("*.json")):
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    traces.append(ExecutionTrace.from_dict(data))
                except Exception:
                    pass
        self._cache = traces
        return traces
    
    def invalidate_cache(self) -> None:
        """Clear the trace cache (call after new traces are written)."""
        self._cache = None
    
    def filter(
        self,
        task: Optional[str] = None,
        trigger: Optional[str] = None,
        status: Optional[str] = None,
        agent_name: Optional[str] = None,
        min_duration_ms: Optional[float] = None,
        max_duration_ms: Optional[float] = None,
        has_errors: Optional[bool] = None,
        tag: Optional[str] = None,
    ) -> list[ExecutionTrace]:
        """Filter traces by criteria.
        
        All criteria are ANDed together.
        """
        traces = self.load_all()
        results = []
        
        for t in traces:
            if task and task.lower() not in (t.task or "").lower():
                continue
            if trigger and t.trigger != trigger:
                continue
            if status and t.status.value != status:
                continue
            if min_duration_ms and (t.duration_ms or 0) < min_duration_ms:
                continue
            if max_duration_ms and (t.duration_ms or 0) > max_duration_ms:
                continue
            
            if agent_name:
                agent_names = {s.name for s in t.agent_spans}
                if agent_name not in agent_names:
                    continue
            
            if has_errors is not None:
                has_err = any(s.status == SpanStatus.FAILED for s in t.spans)
                if has_errors != has_err:
                    continue
            
            if tag:
                all_tags = set()
                for s in t.spans:
                    all_tags.update(getattr(s, 'tags', []))
                if tag not in all_tags:
                    continue
            
            results.append(t)
        
        return results
    
    def agent_stats(self) -> dict[str, dict]:
        """Compute per-agent statistics across all traces.
        
        Returns dict keyed by agent name with:
        - executions: total count
        - success_rate: fraction of successful executions
        - avg_duration_ms: average execution time
        - max_duration_ms: worst case execution time
        - error_types: set of error messages seen
        """
        traces = self.load_all()
        agent_data: dict[str, dict] = {}
        
        for t in traces:
            for s in t.agent_spans:
                name = s.name
                if name not in agent_data:
                    agent_data[name] = {
                        "executions": 0, "successes": 0,
                        "durations": [], "errors": set(),
                    }
                
                d = agent_data[name]
                d["executions"] += 1
                if s.status == SpanStatus.COMPLETED:
                    d["successes"] += 1
                if s.duration_ms is not None:
                    d["durations"].append(s.duration_ms)
                if s.error:
                    d["errors"].add(s.error)
        
        # Compile stats
        stats = {}
        for name, d in agent_data.items():
            durs = d["durations"]
            stats[name] = {
                "executions": d["executions"],
                "success_rate": d["successes"] / max(d["executions"], 1),
                "avg_duration_ms": sum(durs) / len(durs) if durs else 0,
                "max_duration_ms": max(durs) if durs else 0,
                "error_types": list(d["errors"]),
            }
        
        return stats
    
    def tool_stats(self) -> dict[str, dict]:
        """Compute per-tool statistics across all traces."""
        traces = self.load_all()
        tool_data: dict[str, dict] = {}
        
        for t in traces:
            for s in t.tool_spans:
                name = s.name
                if name not in tool_data:
                    tool_data[name] = {
                        "calls": 0, "successes": 0,
                        "durations": [], "errors": set(),
                    }
                d = tool_data[name]
                d["calls"] += 1
                if s.status == SpanStatus.COMPLETED:
                    d["successes"] += 1
                if s.duration_ms is not None:
                    d["durations"].append(s.duration_ms)
                if s.error:
                    d["errors"].add(s.error)
        
        stats = {}
        for name, d in tool_data.items():
            durs = d["durations"]
            stats[name] = {
                "calls": d["calls"],
                "success_rate": d["successes"] / max(d["calls"], 1),
                "avg_duration_ms": sum(durs) / len(durs) if durs else 0,
                "error_types": list(d["errors"]),
            }
        
        return stats
