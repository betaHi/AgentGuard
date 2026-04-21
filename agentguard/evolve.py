"""Self-reflection and evolution engine.

After recording and analyzing traces, this module can:
1. Reflect — identify recurring patterns (failures, bottlenecks, handoff issues)
2. Learn — accumulate knowledge from past traces into a persistent knowledge base
3. Suggest — recommend configuration changes to improve agent performance
4. Evolve — automatically apply lessons to future runs

Inspired by:
- A-MEM: Zettelkasten-style knowledge cards that accumulate over time
- EvoAgentX: self-evolving agent workflows
- Karpathy autoresearch: learn from experiments automatically

Usage:
    from agentguard.evolve import EvolutionEngine

    engine = EvolutionEngine()

    # After a trace is captured:
    reflection = engine.reflect(trace)
    print(reflection.lessons)

    # Accumulate knowledge across runs:
    engine.learn(trace)

    # Get improvement suggestions:
    suggestions = engine.suggest()
"""



from __future__ import annotations

import contextlib
import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from agentguard.analysis import (
    analyze_bottleneck,
    analyze_context_flow,
    analyze_failures,
    analyze_flow,
)
from agentguard.core.trace import ExecutionTrace
from agentguard.scoring import score_trace

__all__ = ['Lesson', 'Reflection', 'KnowledgeBase', 'EvolutionEngine']


@dataclass
class Lesson:
    """A single lesson learned from trace analysis."""
    category: str  # "failure", "bottleneck", "handoff", "pattern"
    agent: str  # which agent this applies to
    observation: str  # what was observed
    suggestion: str  # what to do about it
    confidence: float  # 0-1, increases with repeated observations
    occurrences: int = 1
    first_seen: str = ""
    last_seen: str = ""
    evidence: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "category": self.category, "agent": self.agent,
            "observation": self.observation, "suggestion": self.suggestion,
            "confidence": round(self.confidence, 2),
            "occurrences": self.occurrences,
            "first_seen": self.first_seen, "last_seen": self.last_seen,
            "evidence": self.evidence,
        }


@dataclass
class Reflection:
    """Result of reflecting on a single trace."""
    trace_id: str
    lessons: list[Lesson] = field(default_factory=list)
    patterns_detected: list[str] = field(default_factory=list)
    improvement_score: float = 0.0  # -1 to 1 vs previous traces

    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "lessons": [l.to_dict() for l in self.lessons],
            "patterns": self.patterns_detected,
            "improvement_score": round(self.improvement_score, 2),
        }

    def to_report(self) -> str:
        lines = [
            "# Reflection Report",
            "",
            f"Trace: {self.trace_id}",
            f"Lessons: {len(self.lessons)}",
            f"Patterns: {len(self.patterns_detected)}",
            "",
        ]
        for l in self.lessons:
            icon = {"failure": "🔴", "bottleneck": "🐢", "handoff": "🔀", "pattern": "📊"}.get(l.category, "•")
            lines.append(f"{icon} **{l.agent}** — {l.observation}")
            lines.append(f"   → {l.suggestion}")
            if l.occurrences > 1:
                lines.append(f"   (seen {l.occurrences}x, confidence: {l.confidence:.0%})")
            lines.append("")
        if self.patterns_detected:
            lines.append("## Patterns")
            for p in self.patterns_detected:
                lines.append(f"- {p}")
        return "\n".join(lines)


@dataclass
class KnowledgeBase:
    """Persistent knowledge accumulated from trace analysis.

    Like A-MEM's Zettelkasten, but specialized for agent orchestration.
    Each lesson is a 'card' that gets reinforced with repeated observations.
    """
    lessons: dict[str, Lesson] = field(default_factory=dict)  # key = category:agent:observation_hash
    trace_count: int = 0
    last_updated: str = ""
    best_scores: dict[str, dict] = field(default_factory=dict)  # key = task, value = {score, trace_id, ...}

    def to_dict(self) -> dict:
        return {
            "trace_count": self.trace_count,
            "last_updated": self.last_updated,
            "lesson_count": len(self.lessons),
            "lessons": {k: v.to_dict() for k, v in self.lessons.items()},
            "best_scores": self.best_scores,
        }

    @classmethod
    def from_dict(cls, data: dict) -> KnowledgeBase:
        kb = cls(
            trace_count=data.get("trace_count", 0),
            last_updated=data.get("last_updated", ""),
            best_scores=data.get("best_scores", {}),
        )
        for k, v in data.get("lessons", {}).items():
            kb.lessons[k] = Lesson(**{f: v[f] for f in Lesson.__dataclass_fields__ if f in v})
        return kb


class EvolutionEngine:
    """Self-reflection and learning engine for agent orchestration.

    Accumulates knowledge across traces and produces actionable suggestions.
    """

    def __init__(self, knowledge_dir: str = ".agentguard/knowledge"):
        self.knowledge_dir = Path(knowledge_dir)
        self._kb: KnowledgeBase | None = None
        self._load_warning: str | None = None

    @property
    def load_warning(self) -> str | None:
        """Return any warning produced while loading the knowledge base."""
        return self._load_warning

    def _quarantine_corrupt_kb(self, kb_path: Path) -> None:
        """Move an unreadable knowledge base aside so a clean one can be rebuilt."""
        suffix = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        backup = kb_path.with_name(f"knowledge.corrupt.{suffix}.json")
        with contextlib.suppress(OSError):
            kb_path.replace(backup)

    def _load_kb_from_disk(self) -> KnowledgeBase:
        """Load knowledge safely, recovering from corrupt on-disk state."""
        kb_path = self.knowledge_dir / "knowledge.json"
        if not kb_path.exists():
            self._load_warning = None
            return KnowledgeBase()
        try:
            data = json.loads(kb_path.read_text(encoding="utf-8"))
            self._load_warning = None
            return KnowledgeBase.from_dict(data)
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            self._load_warning = f"Recovered corrupt knowledge base: {exc}"
            self._quarantine_corrupt_kb(kb_path)
            return KnowledgeBase()

    @property
    def kb(self) -> KnowledgeBase:
        """Load or create the knowledge base."""
        if self._kb is None:
            self._kb = self._load_kb_from_disk()
        return self._kb

    def _save_kb(self) -> None:
        """Persist the knowledge base to disk."""
        self.knowledge_dir.mkdir(parents=True, exist_ok=True)
        kb_path = self.knowledge_dir / "knowledge.json"
        tmp_path = kb_path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(self.kb.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        tmp_path.replace(kb_path)

    def _lesson_key(self, lesson: Lesson) -> str:
        """Build a stable deduplication key for a lesson across processes."""
        raw = f"{lesson.category}|{lesson.agent}|{lesson.observation}".encode("utf-8")
        digest = hashlib.sha1(raw).hexdigest()[:12]
        return f"{lesson.category}:{lesson.agent}:{digest}"

    def _lesson_evidence(self, trace: ExecutionTrace, lesson: Lesson, now: str) -> dict[str, str]:
        """Build a compact evidence entry for a learned lesson."""
        return {
            "trace_id": trace.trace_id,
            "task": trace.task or "",
            "span": lesson.agent,
            "observed_at": now,
        }

    def _validate_confidence(self, min_confidence: float) -> None:
        """Validate confidence threshold arguments."""
        if not 0 <= min_confidence <= 1:
            raise ValueError("min_confidence must be between 0 and 1")

    def _validate_positive(self, value: int, name: str) -> None:
        """Validate positive integer arguments."""
        if value < 1:
            raise ValueError(f"{name} must be >= 1")

    def _load_auto_apply_config(self, config_path: Path) -> dict:
        """Load config safely before auto-apply writes changes."""
        if not config_path.exists():
            return {}
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid config JSON in {config_path}: {exc.msg}") from exc
        if not isinstance(config, dict):
            raise ValueError(f"Invalid config format in {config_path}: root must be an object")
        if "agents" in config and not isinstance(config["agents"], list):
            raise ValueError(f"Invalid config format in {config_path}: 'agents' must be a list")
        return config

    def _lessons_from_failures(
        self, failures: "FailureAnalysis", now: str,
    ) -> list["Lesson"]:
        """Extract lessons from failure root causes."""
        lessons = []
        for rc in failures.root_causes:
            if not rc.was_handled:
                lessons.append(Lesson(
                    category="failure", agent=rc.span_name,
                    observation=f"Unhandled failure: {rc.error[:80]}",
                    suggestion=f"Add try/except with fallback in '{rc.span_name}', or add a retry mechanism",
                    confidence=0.7, first_seen=now, last_seen=now,
                ))
            else:
                lessons.append(Lesson(
                    category="failure", agent=rc.span_name,
                    observation=f"Failure handled gracefully: {rc.error[:80]}",
                    suggestion=f"Good: '{rc.span_name}' has fallback. Consider adding monitoring for failure rate.",
                    confidence=0.5, first_seen=now, last_seen=now,
                ))
        return lessons

    def _lessons_from_context(
        self, ctx: "ContextFlowResult", now: str,
    ) -> list["Lesson"]:
        """Extract lessons from context flow anomalies."""
        lessons = []
        for anomaly in ctx.anomalies:
            if anomaly.anomaly == "loss":
                lessons.append(Lesson(
                    category="handoff", agent=anomaly.to_agent,
                    observation=f"Context loss: keys {anomaly.keys_lost} lost in handoff from {anomaly.from_agent}",
                    suggestion=f"Ensure '{anomaly.from_agent}' passes all required keys, or add validation at '{anomaly.to_agent}' input",
                    confidence=0.8, first_seen=now, last_seen=now,
                ))
            elif anomaly.anomaly == "bloat":
                lessons.append(Lesson(
                    category="handoff", agent=anomaly.from_agent,
                    observation=f"Context bloat: +{anomaly.size_delta_bytes:,}B between {anomaly.from_agent} → {anomaly.to_agent}",
                    suggestion="Consider filtering or summarizing output before handoff to reduce context size",
                    confidence=0.5, first_seen=now, last_seen=now,
                ))
        return lessons

    def reflect(self, trace: ExecutionTrace) -> Reflection:
        """Reflect on a single trace and extract lessons and patterns."""
        now = datetime.now(UTC).isoformat()
        reflection = Reflection(trace_id=trace.trace_id)

        failures = analyze_failures(trace)
        flow = analyze_flow(trace)
        bn = analyze_bottleneck(trace) if trace.agent_spans else None
        ctx = analyze_context_flow(trace)

        reflection.lessons.extend(self._lessons_from_failures(failures, now))

        if bn and bn.bottleneck_pct > 30 and len(trace.agent_spans) > 1:
            reflection.lessons.append(Lesson(
                category="bottleneck", agent=bn.bottleneck_span,
                observation=f"Agent consumes {bn.bottleneck_pct:.0f}% of total execution time",
                suggestion=f"Consider: parallelize internal operations, cache results, or use a faster model for '{bn.bottleneck_span}'",
                confidence=0.6, first_seen=now, last_seen=now,
            ))

        reflection.lessons.extend(self._lessons_from_context(ctx, now))

        if failures.total_failed_spans > 0 and failures.resilience_score < 0.5:
            reflection.patterns_detected.append(
                f"Low resilience ({failures.resilience_score:.0%}): {failures.unhandled_count} unhandled failures out of {len(failures.root_causes)} root causes"
            )
        if flow.critical_path and len(flow.critical_path) > 4:
            reflection.patterns_detected.append(
                f"Long critical path ({len(flow.critical_path)} steps): consider parallelizing independent agents"
            )
        return reflection

    def learn(self, trace: ExecutionTrace) -> Reflection:
        """Reflect on a trace AND accumulate lessons into the knowledge base.

        This is reflect + persist. Repeated observations increase confidence.
        """
        reflection = self.reflect(trace)
        now = datetime.now(UTC).isoformat()

        for lesson in reflection.lessons:
            key = self._lesson_key(lesson)
            evidence = self._lesson_evidence(trace, lesson, now)

            if key in self.kb.lessons:
                # Reinforce existing lesson
                existing = self.kb.lessons[key]
                existing.occurrences += 1
                existing.last_seen = now
                existing.evidence = (existing.evidence + [evidence])[-5:]
                # Confidence increases with repetition (caps at 0.95)
                existing.confidence = min(0.95, existing.confidence + 0.05)
            else:
                # New lesson
                lesson.first_seen = now
                lesson.last_seen = now
                lesson.evidence = [evidence]
                self.kb.lessons[key] = lesson

        self.kb.trace_count += 1
        self.kb.last_updated = now
        self._save_kb()

        return reflection

    def suggest(self, min_confidence: float = 0.5) -> list[Lesson]:
        """Get improvement suggestions from accumulated knowledge.

        Returns lessons sorted by confidence (most confident first).
        Only returns lessons above the confidence threshold.
        """
        self._validate_confidence(min_confidence)
        suggestions = [
            l for l in self.kb.lessons.values()
            if l.confidence >= min_confidence
        ]
        return sorted(suggestions, key=lambda l: (-l.confidence, -l.occurrences))





    def agent_performance_history(self) -> dict[str, list[dict]]:
        """Get per-agent performance across all learned traces.

        Returns dict keyed by agent name with list of:
        {duration_ms, status, trace_id, timestamp}
        """
        history: dict[str, list[dict]] = {}

        for _key, lesson in self.kb.lessons.items():
            agent = lesson.agent
            if agent not in history:
                history[agent] = []
            history[agent].append({
                "category": lesson.category,
                "observation": lesson.observation,
                "confidence": lesson.confidence,
                "occurrences": lesson.occurrences,
                "last_seen": lesson.last_seen,
            })

        return history



    def compare_to_best(self, current_trace: ExecutionTrace) -> dict:
        """Compare current trace against the historical best for this pipeline.

        Tracks the best score per task (pipeline name). Returns whether the
        current trace is an improvement, regression, or stable compared to
        the best recorded run.

        Args:
            current_trace: The trace to compare.

        Returns:
            Dict with trend, current_score, best_score, delta, and details.
        """
        current_score = score_trace(current_trace)
        task_key = current_trace.task or "__default__"

        best = self.kb.best_scores.get(task_key)
        best_overall = best["score"] if best else None

        # Update best if current is better
        if best_overall is None or current_score.overall > best_overall:
            self.kb.best_scores[task_key] = {
                "score": round(current_score.overall, 1),
                "grade": current_score.grade,
                "trace_id": current_trace.trace_id,
                "timestamp": datetime.now(UTC).isoformat(),
            }
            self._save_kb()

        if best_overall is None:
            trend = "first_run"
            delta = 0.0
        else:
            delta = current_score.overall - best_overall
            if delta > 5:
                trend = "improving"
            elif delta < -10:
                trend = "regression"
            else:
                trend = "stable"

        return {
            "trend": trend,
            "current_score": round(current_score.overall, 1),
            "current_grade": current_score.grade,
            "best_score": best_overall,
            "best_trace_id": best["trace_id"] if best else None,
            "delta": round(delta, 1),
            "task": task_key,
        }

    def detect_trends(self, window: int = 10) -> list[dict]:
        """Detect improving/degrading trends across recent traces.

        Compares recent lessons against historical baseline to detect:
        - Agents getting worse (more failures, more bottleneck time)
        - Agents getting better (fewer failures, faster execution)
        - New issues appearing
        - Old issues resolving

        Args:
            window: Number of recent traces to analyze.

        Returns:
            List of trend observations.
        """
        self._validate_positive(window, "window")
        trends = []

        lessons = sorted(
            self.kb.lessons.values(),
            key=lambda lesson: lesson.last_seen,
            reverse=True,
        )[:window]

        for lesson in lessons:
            if lesson.occurrences >= 3:
                if lesson.category == "failure" and "unhandled" in lesson.observation.lower():
                    trends.append({
                        "type": "recurring_failure",
                        "agent": lesson.agent,
                        "severity": "high",
                        "message": f"'{lesson.agent}' has had {lesson.occurrences} unhandled failures — needs immediate attention",
                        "occurrences": lesson.occurrences,
                    })
                elif lesson.category == "bottleneck":
                    trends.append({
                        "type": "persistent_bottleneck",
                        "agent": lesson.agent,
                        "severity": "medium",
                        "message": f"'{lesson.agent}' is consistently the bottleneck ({lesson.occurrences} times)",
                        "occurrences": lesson.occurrences,
                    })

            # New issue (seen only once, recently)
            if lesson.occurrences == 1 and lesson.confidence >= 0.6:
                trends.append({
                    "type": "new_issue",
                    "agent": lesson.agent,
                    "severity": "low",
                    "message": f"New: {lesson.observation}",
                    "occurrences": 1,
                })

        return sorted(trends, key=lambda t: {"high": 0, "medium": 1, "low": 2}.get(t["severity"], 3))


    def generate_prd(self, min_occurrences: int = 3) -> str:
        """Auto-generate an improvement PRD from recurring failure patterns.

        Args:
            min_occurrences: Minimum times a pattern must recur to be included.

        Returns:
            Markdown-formatted PRD string.
        """
        self._validate_positive(min_occurrences, "min_occurrences")
        recurring = [l for l in self.kb.lessons.values() if l.occurrences >= min_occurrences]
        if not recurring:
            return (
                "# Improvement PRD\n\n"
                f"No recurring patterns (threshold: {min_occurrences}+).\n"
                f"Analyzed {self.kb.trace_count} traces, {len(self.kb.lessons)} lessons."
            )

        by_cat: dict[str, list[Lesson]] = {}
        for l in recurring:
            by_cat.setdefault(l.category, []).append(l)
        for cat in by_cat:
            by_cat[cat].sort(key=lambda l: l.confidence * l.occurrences, reverse=True)

        prio = {"failure": "P0", "bottleneck": "P1", "handoff": "P1", "score": "P2"}
        icons = {"failure": "\U0001f534", "bottleneck": "\U0001f422", "handoff": "\U0001f500", "score": "\U0001f4ca"}

        lines = [
            "# AgentGuard Improvement PRD", "",
            f"> From {self.kb.trace_count} traces, {len(recurring)} recurring patterns.", "",
            "## Executive Summary", "",
            f"{len(recurring)} recurring issues across {len(set(l.agent for l in recurring))} agents.", "",
        ]
        n = 0
        for cat, lessons in sorted(by_cat.items(), key=lambda kv: {"failure": 0, "bottleneck": 1, "handoff": 2}.get(kv[0], 3)):
            icon = icons.get(cat, "\u2022")
            lines.append(f"## {icon} {cat.title()} ({prio.get(cat, 'P3')})")
            lines.append("")
            for l in lessons:
                n += 1
                lines.append(f"### {n}. {l.agent}")
                lines.append(f"- **Problem:** {l.observation}")
                lines.append(f"- **Frequency:** {l.occurrences}x (confidence: {l.confidence:.0%})")
                lines.append(f"- **Fix:** {l.suggestion}")
                lines.append("")

        best_val = max((b.get("score", 0) for b in self.kb.best_scores.values()), default="N/A")
        lines.extend(["## Success Criteria", "",
            "- [ ] Zero recurring unhandled failures",
            "- [ ] Bottleneck agents show latency improvement",
            f"- [ ] Trace score above 80/100 (best: {best_val})", ""])
        return "\n".join(lines)

    def auto_apply(self, trace: ExecutionTrace, min_confidence: float = 0.8, dry_run: bool = True) -> dict:
        """Generate and optionally apply high-confidence config patches.

        Args:
            trace: Current trace to analyze.
            min_confidence: Threshold for suggestions.
            dry_run: If True, return patches without writing.

        Returns:
            Dict with patches, scores, and status.
        """
        self._validate_confidence(min_confidence)
        suggestions = self.suggest(min_confidence=min_confidence)
        if not suggestions:
            return {"status": "no_suggestions", "patches": []}

        patches = []
        for s in suggestions:
            patch = {"agent": s.agent, "category": s.category, "confidence": s.confidence,
                     "occurrences": s.occurrences, "suggestion": s.suggestion}
            if s.category == "failure":
                patch["config"] = {"retry_policy": {"max_retries": 3, "backoff_ms": 1000}, "fallback": True}
            elif s.category == "bottleneck":
                patch["config"] = {"timeout_ms": 30000, "parallel": True, "cache": True}
            elif s.category == "handoff":
                patch["config"] = {"validate_context": True, "required_keys": []}
            else:
                patch["config"] = {}
            patches.append(patch)

        sc = score_trace(trace)
        cmp = self.compare_to_best(trace)
        result = {"status": "dry_run" if dry_run else "applied", "patches": patches,
                  "patch_count": len(patches), "current_score": sc.overall,
                  "current_grade": sc.grade, "best_score": cmp.get("best_score"), "trend": cmp["trend"]}

        if not dry_run:
            cp = Path("agentguard.json")
            cfg = self._load_auto_apply_config(cp)
            ac = {a.get("name", ""): a for a in cfg.get("agents", [])}
            for p in patches:
                nm = p["agent"]
                if nm not in ac: ac[nm] = {"name": nm}
                ac[nm].update(p["config"])
            cfg["agents"] = list(ac.values())
            cfg["_auto_applied"] = datetime.now(UTC).isoformat()
            cp.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            result["config_path"] = str(cp)
        return result

    def summary(self) -> str:
        """Generate a human-readable summary of accumulated knowledge."""
        lines = [
            "# Evolution Knowledge Base",
            "",
            f"- Traces analyzed: {self.kb.trace_count}",
            f"- Lessons learned: {len(self.kb.lessons)}",
            f"- Last updated: {self.kb.last_updated}",
            "",
        ]

        suggestions = self.suggest()
        if suggestions:
            lines.append("## Top Suggestions")
            lines.append("")
            for l in suggestions[:10]:
                icon = {"failure": "🔴", "bottleneck": "🐢", "handoff": "🔀", "pattern": "📊"}.get(l.category, "•")
                lines.append(f"{icon} **{l.agent}** ({l.confidence:.0%} confidence, seen {l.occurrences}x)")
                lines.append(f"   {l.observation}")
                lines.append(f"   → {l.suggestion}")
                lines.append("")
        else:
            lines.append("No suggestions yet. Analyze more traces to accumulate knowledge.")

        return "\n".join(lines)
