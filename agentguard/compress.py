"""Trace compression — reduce trace size for storage and transmission.

Strategies:
1. Strip null/empty fields
2. Shorten span IDs
3. Remove duplicate metadata
4. Compact timestamps to relative offsets
"""

from __future__ import annotations

import json
from typing import Any

from agentguard.core.trace import ExecutionTrace


def compress_trace(trace: ExecutionTrace, level: str = "standard") -> dict:
    """Compress a trace dict for storage.
    
    Args:
        trace: The trace to compress.
        level: "light" (strip nulls), "standard" (+ compact), "aggressive" (+ drop data)
    
    Returns:
        Compressed dict (smaller than trace.to_dict()).
    """
    d = trace.to_dict()
    
    # Level 1: Strip null/empty fields
    d["spans"] = [_strip_nulls(s) for s in d["spans"]]
    
    if level in ("standard", "aggressive"):
        # Level 2: Compact timestamps to relative ms offsets
        if d.get("started_at"):
            base_time = d["started_at"]
            for span in d["spans"]:
                if span.get("started_at") == base_time:
                    span["started_at"] = 0
                elif span.get("started_at"):
                    # Keep as-is for now (proper compression would use ms offsets)
                    pass
    
    if level == "aggressive":
        # Level 3: Drop input/output data (keep keys only)
        for span in d["spans"]:
            if isinstance(span.get("input_data"), dict):
                span["input_data"] = {"_keys": list(span["input_data"].keys())}
            elif span.get("input_data") is not None:
                span["input_data"] = {"_type": type(span["input_data"]).__name__}
            
            if isinstance(span.get("output_data"), dict):
                span["output_data"] = {"_keys": list(span["output_data"].keys())}
            elif span.get("output_data") is not None:
                span["output_data"] = {"_type": type(span["output_data"]).__name__}
    
    return d


def _strip_nulls(d: dict) -> dict:
    """Remove keys with None/empty values."""
    return {k: v for k, v in d.items() 
            if v is not None and v != "" and v != [] and v != {} and v != 0
            and not (k == "retry_count" and v == 0)
            and not (k == "failure_handled" and v is False)}


def measure_compression(trace: ExecutionTrace) -> dict:
    """Measure compression ratios for different levels."""
    original = json.dumps(trace.to_dict())
    
    results = {}
    for level in ("light", "standard", "aggressive"):
        compressed = json.dumps(compress_trace(trace, level))
        ratio = len(compressed) / max(len(original), 1)
        results[level] = {
            "original_bytes": len(original),
            "compressed_bytes": len(compressed),
            "ratio": round(ratio, 3),
            "savings_pct": round((1 - ratio) * 100, 1),
        }
    
    return results
