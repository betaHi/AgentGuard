"""Rule-based evaluation assertions.

Built-in rule types:
- min_count: minimum number of items
- max_count: maximum number of items
- each_has: all items have required fields
- recency: dates within N days
- no_duplicates: unique values on a field
- contains: output contains substring/keyword
- regex: output matches regex pattern
- range: numeric value within range
- custom: user-defined callable
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from agentguard.core.eval_schema import RuleResult, RuleVerdict


def _resolve_path(data: Any, path: str) -> Any:
    """Resolve a dot-separated path in nested data.

    Examples:
        _resolve_path({"a": {"b": [1,2]}}, "a.b") → [1, 2]
        _resolve_path([{"x": 1}, {"x": 2}], "x") → [1, 2]  (maps over list)
    """
    if not path:
        return data

    parts = path.split(".", 1)
    key = parts[0]
    rest = parts[1] if len(parts) > 1 else ""

    if isinstance(data, dict):
        if key in data:
            return _resolve_path(data[key], rest)
        return None
    elif isinstance(data, (list, tuple)):
        # Map over list items
        results = []
        for item in data:
            val = _resolve_path(item, path)
            if val is not None:
                if isinstance(val, list):
                    results.extend(val)
                else:
                    results.append(val)
        return results if results else None

    return None


def eval_min_count(data: Any, target: str, value: int, **_) -> RuleResult:
    """Check that target has at least `value` items."""
    resolved = _resolve_path(data, target)
    if resolved is None:
        return RuleResult(name=f"min_count({target})", rule_type="min_count",
                         verdict=RuleVerdict.FAIL, expected=f">= {value}", actual="None (path not found)")

    count = len(resolved) if isinstance(resolved, (list, tuple)) else 1
    passed = count >= value
    return RuleResult(
        name=f"min_count({target})", rule_type="min_count",
        verdict=RuleVerdict.PASS if passed else RuleVerdict.FAIL,
        expected=f">= {value}", actual=count,
        detail=f"Found {count} items" if passed else f"Expected >= {value}, found {count}"
    )


def eval_max_count(data: Any, target: str, value: int, **_) -> RuleResult:
    """Check that target has at most `value` items."""
    resolved = _resolve_path(data, target)
    count = len(resolved) if isinstance(resolved, (list, tuple)) else (0 if resolved is None else 1)
    passed = count <= value
    return RuleResult(
        name=f"max_count({target})", rule_type="max_count",
        verdict=RuleVerdict.PASS if passed else RuleVerdict.FAIL,
        expected=f"<= {value}", actual=count,
    )


def eval_each_has(data: Any, target: str, fields: list[str], **_) -> RuleResult:
    """Check all items in target have the specified fields."""
    resolved = _resolve_path(data, target)
    if not isinstance(resolved, (list, tuple)):
        return RuleResult(name=f"each_has({target})", rule_type="each_has",
                         verdict=RuleVerdict.FAIL, detail="Target is not a list")

    missing = []
    for i, item in enumerate(resolved):
        if not isinstance(item, dict):
            missing.append(f"item[{i}] is not a dict")
            continue
        for f in fields:
            if f not in item or item[f] is None:
                missing.append(f"item[{i}] missing '{f}'")

    return RuleResult(
        name=f"each_has({target})", rule_type="each_has",
        verdict=RuleVerdict.PASS if not missing else RuleVerdict.FAIL,
        expected=f"all items have {fields}",
        actual=f"{len(missing)} missing" if missing else "all present",
        detail="; ".join(missing[:5]) if missing else "",
    )


def eval_recency(data: Any, target: str, within_days: int, **_) -> RuleResult:
    """Check that date values are within N days of now."""
    resolved = _resolve_path(data, target)
    if resolved is None:
        return RuleResult(name=f"recency({target})", rule_type="recency",
                         verdict=RuleVerdict.FAIL, detail="Target not found")

    if not isinstance(resolved, list):
        resolved = [resolved]

    now = datetime.now(UTC)
    cutoff = now - timedelta(days=within_days)
    stale = []

    for i, val in enumerate(resolved):
        try:
            if isinstance(val, str):
                dt = None
                # Try ISO format with timezone first
                try:
                    dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=UTC)
                except (ValueError, TypeError):
                    pass

                # Try common date-only formats
                if dt is None:
                    for fmt in ["%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y"]:
                        try:
                            dt = datetime.strptime(val, fmt).replace(tzinfo=UTC)
                            break
                        except (ValueError, TypeError):
                            continue

                if dt is None:
                    stale.append(f"item[{i}]: unparseable date \'{val}\'")
                    continue

                if dt < cutoff:
                    stale.append(f"item[{i}]: {val} is older than {within_days} days")
        except Exception as e:
            stale.append(f"item[{i}]: error parsing \'{val}\': {e}")

    return RuleResult(
        name=f"recency({target})", rule_type="recency",
        verdict=RuleVerdict.PASS if not stale else RuleVerdict.FAIL,
        expected=f"within {within_days} days",
        actual=f"{len(stale)} stale" if stale else "all recent",
        detail="; ".join(stale[:3]) if stale else "",
    )


def eval_no_duplicates(data: Any, target: str, field: str | None = None, **_) -> RuleResult:
    """Check for unique values."""
    resolved = _resolve_path(data, target)
    if not isinstance(resolved, (list, tuple)):
        return RuleResult(name=f"no_duplicates({target})", rule_type="no_duplicates",
                         verdict=RuleVerdict.FAIL, detail="Target is not a list")

    values = [_resolve_path(item, field) for item in resolved if isinstance(item, dict)] if field else list(resolved)

    seen = set()
    dupes = []
    for v in values:
        key = str(v)
        if key in seen:
            dupes.append(key)
        seen.add(key)

    return RuleResult(
        name=f"no_duplicates({target})", rule_type="no_duplicates",
        verdict=RuleVerdict.PASS if not dupes else RuleVerdict.FAIL,
        expected="all unique", actual=f"{len(dupes)} duplicates",
        detail=f"Duplicates: {dupes[:3]}" if dupes else "",
    )


def eval_contains(data: Any, target: str, keywords: list[str], mode: str = "any", **_) -> RuleResult:
    """Check that target contains specified keywords."""
    resolved = _resolve_path(data, target)
    text = str(resolved).lower() if resolved else ""

    found = [kw for kw in keywords if kw.lower() in text]

    if mode == "all":
        passed = len(found) == len(keywords)
        missing = [kw for kw in keywords if kw not in found]
        detail = f"Missing: {missing}" if not passed else ""
    else:  # any
        passed = len(found) > 0
        detail = f"Found: {found}" if passed else f"None of {keywords} found"

    return RuleResult(
        name=f"contains({target})", rule_type="contains",
        verdict=RuleVerdict.PASS if passed else RuleVerdict.FAIL,
        expected=f"{mode} of {keywords}", actual=f"found {found}",
        detail=detail,
    )


def eval_regex(data: Any, target: str, pattern: str, **_) -> RuleResult:
    """Check that target matches a regex pattern."""
    resolved = _resolve_path(data, target)
    text = str(resolved) if resolved else ""

    match = bool(re.search(pattern, text))
    return RuleResult(
        name=f"regex({target})", rule_type="regex",
        verdict=RuleVerdict.PASS if match else RuleVerdict.FAIL,
        expected=f"matches /{pattern}/", actual=f"{'matched' if match else 'no match'}",
    )


def eval_range(data: Any, target: str, min_val: float | None = None, max_val: float | None = None, **_) -> RuleResult:
    """Check numeric value is within range."""
    resolved = _resolve_path(data, target)
    try:
        val = float(resolved) if resolved is not None else None
    except (ValueError, TypeError):
        return RuleResult(name=f"range({target})", rule_type="range",
                         verdict=RuleVerdict.FAIL, detail=f"Not a number: {resolved}")

    if val is None:
        return RuleResult(name=f"range({target})", rule_type="range",
                         verdict=RuleVerdict.FAIL, detail="Value is None")

    passed = True
    if min_val is not None and val < min_val:
        passed = False
    if max_val is not None and val > max_val:
        passed = False

    expected = f"[{min_val or '-∞'}, {max_val or '+∞'}]"
    return RuleResult(
        name=f"range({target})", rule_type="range",
        verdict=RuleVerdict.PASS if passed else RuleVerdict.FAIL,
        expected=expected, actual=val,
    )


# Rule registry
RULE_REGISTRY: dict[str, Callable] = {
    "min_count": eval_min_count,
    "max_count": eval_max_count,
    "each_has": eval_each_has,
    "recency": eval_recency,
    "no_duplicates": eval_no_duplicates,
    "contains": eval_contains,
    "regex": eval_regex,
    "range": eval_range,
}


def evaluate_rules(data: Any, rules: list[dict]) -> list[RuleResult]:
    """Evaluate a list of rule definitions against data.

    Args:
        data: The agent output to evaluate.
        rules: List of rule dicts, each with 'type' and rule-specific params.

    Returns:
        List of RuleResult objects.
    """
    results = []
    for rule_def in rules:
        rule_type = rule_def.get("type", "")
        rule_fn = RULE_REGISTRY.get(rule_type)

        if rule_fn is None:
            results.append(RuleResult(
                name=rule_def.get("name", rule_type),
                rule_type=rule_type,
                verdict=RuleVerdict.ERROR,
                detail=f"Unknown rule type: {rule_type}",
            ))
            continue

        try:
            result = rule_fn(data, **{k: v for k, v in rule_def.items() if k != "type"})
            if rule_def.get("name"):
                result.name = rule_def["name"]
            results.append(result)
        except Exception as e:
            results.append(RuleResult(
                name=rule_def.get("name", rule_type),
                rule_type=rule_type,
                verdict=RuleVerdict.ERROR,
                detail=f"Rule execution error: {e}",
            ))

    return results
