"""Trace store — file-based storage and retrieval of traces.

Provides a simple file-based store for persisting and querying traces:
- Save/load individual traces
- List all traces with metadata
- Query by time range, task, or status
- Automatic trace pruning (keep last N)
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from agentguard.core.trace import ExecutionTrace, SpanStatus


@dataclass
class TraceInfo:
    """Lightweight metadata about a stored trace."""
    trace_id: str
    task: str
    status: str
    started_at: str
    ended_at: Optional[str]
    span_count: int
    file_path: str
    
    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "task": self.task,
            "status": self.status,
            "started_at": self.started_at,
            "span_count": self.span_count,
        }


class TraceStore:
    """File-based trace storage."""
    
    def __init__(self, directory: str = ".agentguard/traces"):
        self._dir = Path(directory)
        self._dir.mkdir(parents=True, exist_ok=True)
    
    def save(self, trace: ExecutionTrace) -> str:
        """Save a trace to disk. Returns the file path."""
        filename = f"{trace.trace_id}.json"
        path = self._dir / filename
        path.write_text(trace.to_json())
        return str(path)
    
    def load(self, trace_id: str) -> Optional[ExecutionTrace]:
        """Load a trace by ID."""
        path = self._dir / f"{trace_id}.json"
        if not path.exists():
            # Try finding by prefix
            matches = list(self._dir.glob(f"{trace_id}*.json"))
            if matches:
                path = matches[0]
            else:
                return None
        
        try:
            return ExecutionTrace.from_json(path.read_text())
        except Exception:
            return None
    
    def list_traces(self, limit: int = 50) -> list[TraceInfo]:
        """List all stored traces with metadata."""
        infos = []
        for path in sorted(self._dir.glob("*.json"), reverse=True):
            try:
                data = json.loads(path.read_text())
                infos.append(TraceInfo(
                    trace_id=data.get("trace_id", path.stem),
                    task=data.get("task", ""),
                    status=data.get("status", "unknown"),
                    started_at=data.get("started_at", ""),
                    ended_at=data.get("ended_at"),
                    span_count=len(data.get("spans", [])),
                    file_path=str(path),
                ))
            except Exception:
                continue
            if len(infos) >= limit:
                break
        return infos
    
    def query(
        self,
        status: Optional[str] = None,
        task_contains: Optional[str] = None,
        limit: int = 50,
    ) -> list[ExecutionTrace]:
        """Query traces by status and/or task."""
        results = []
        for info in self.list_traces(limit=limit * 2):
            if status and info.status != status:
                continue
            if task_contains and task_contains.lower() not in info.task.lower():
                continue
            trace = self.load(info.trace_id)
            if trace:
                results.append(trace)
            if len(results) >= limit:
                break
        return results
    
    def prune(self, keep: int = 100) -> int:
        """Remove oldest traces, keeping only the most recent `keep` files."""
        files = sorted(self._dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        removed = 0
        for path in files[keep:]:
            path.unlink()
            removed += 1
        return removed
    
    @property
    def count(self) -> int:
        """Number of stored traces."""
        return len(list(self._dir.glob("*.json")))
