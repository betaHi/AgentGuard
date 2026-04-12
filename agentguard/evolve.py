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

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from agentguard.core.trace import ExecutionTrace, Span, SpanType, SpanStatus
from agentguard.analysis import (
    analyze_failures, analyze_flow, analyze_bottleneck, analyze_context_flow,
    FailureAnalysis, FlowAnalysis,
)

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

    def to_dict(self) -> dict:
        return {
            "category": self.category, "agent": self.agent,
            "observation": self.observation, "suggestion": self.suggestion,
            "confidence": round(self.confidence, 2),
            "occurrences": self.occurrences,
            "first_seen": self.first_seen, "last_seen": self.last_seen,
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

    def to_dict(self) -> dict:
        return {
            "trace_count": self.trace_count,
            "last_updated": self.last_updated,
            "lesson_count": len(self.lessons),
            "lessons": {k: v.to_dict() for k, v in self.lessons.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> KnowledgeBase:
        kb = cls(
            trace_count=data.get("trace_count", 0),
            last_updated=data.get("last_updated", ""),
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
        self._kb: Optional[KnowledgeBase] = None
    
    @property
    def kb(self) -> KnowledgeBase:
        """Load or create the knowledge base."""
        if self._kb is None:
            kb_path = self.knowledge_dir / "knowledge.json"
            if kb_path.exists():
                self._kb = KnowledgeBase.from_dict(
                    json.loads(kb_path.read_text(encoding="utf-8"))
                )
            else:
                self._kb = KnowledgeBase()
        return self._kb
    
    def _save_kb(self) -> None:
        """Persist the knowledge base to disk."""
        self.knowledge_dir.mkdir(parents=True, exist_ok=True)
        kb_path = self.knowledge_dir / "knowledge.json"
        kb_path.write_text(json.dumps(self.kb.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    
    def reflect(self, trace: ExecutionTrace) -> Reflection:
        """Reflect on a single trace and extract lessons.
        
        This is the 'think' step — analyze what happened and why.
        """
        now = datetime.now(timezone.utc).isoformat()
        reflection = Reflection(trace_id=trace.trace_id)
        
        failures = analyze_failures(trace)
        flow = analyze_flow(trace)
        bn = analyze_bottleneck(trace) if trace.agent_spans else None
        ctx = analyze_context_flow(trace)
        
        # Lesson 1: Unhandled failures — agent needs error handling
        for rc in failures.root_causes:
            if not rc.was_handled:
                reflection.lessons.append(Lesson(
                    category="failure",
                    agent=rc.span_name,
                    observation=f"Unhandled failure: {rc.error[:80]}",
                    suggestion=f"Add try/except with fallback in '{rc.span_name}', or add a retry mechanism",
                    confidence=0.7,
                    first_seen=now, last_seen=now,
                ))
        
        # Lesson 2: Handled failures — good pattern, but track frequency
        for rc in failures.root_causes:
            if rc.was_handled:
                reflection.lessons.append(Lesson(
                    category="failure",
                    agent=rc.span_name,
                    observation=f"Failure handled gracefully: {rc.error[:80]}",
                    suggestion=f"Good: '{rc.span_name}' has fallback. Consider adding monitoring for failure rate.",
                    confidence=0.5,
                    first_seen=now, last_seen=now,
                ))
        
        # Lesson 3: Bottleneck detection
        if bn and bn.bottleneck_pct > 30 and len(trace.agent_spans) > 1:
            reflection.lessons.append(Lesson(
                category="bottleneck",
                agent=bn.bottleneck_span,
                observation=f"Agent consumes {bn.bottleneck_pct:.0f}% of total execution time",
                suggestion=f"Consider: parallelize internal operations, cache results, or use a faster model for '{bn.bottleneck_span}'",
                confidence=0.6,
                first_seen=now, last_seen=now,
            ))
        
        # Lesson 4: Context flow anomalies
        for anomaly in ctx.anomalies:
            if anomaly.anomaly == "loss":
                reflection.lessons.append(Lesson(
                    category="handoff",
                    agent=anomaly.to_agent,
                    observation=f"Context loss: keys {anomaly.keys_lost} lost in handoff from {anomaly.from_agent}",
                    suggestion=f"Ensure '{anomaly.from_agent}' passes all required keys, or add validation at '{anomaly.to_agent}' input",
                    confidence=0.8,
                    first_seen=now, last_seen=now,
                ))
            elif anomaly.anomaly == "bloat":
                reflection.lessons.append(Lesson(
                    category="handoff",
                    agent=anomaly.from_agent,
                    observation=f"Context bloat: +{anomaly.size_delta_bytes:,}B between {anomaly.from_agent} → {anomaly.to_agent}",
                    suggestion=f"Consider filtering or summarizing output before handoff to reduce context size",
                    confidence=0.5,
                    first_seen=now, last_seen=now,
                ))
        
        # Lesson 5: Low resilience pattern
        if failures.total_failed_spans > 0 and failures.resilience_score < 0.5:
            reflection.patterns_detected.append(
                f"Low resilience ({failures.resilience_score:.0%}): {failures.unhandled_count} unhandled failures out of {len(failures.root_causes)} root causes"
            )
        
        # Lesson 6: Long critical path
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
        now = datetime.now(timezone.utc).isoformat()
        
        for lesson in reflection.lessons:
            # Create a stable key for deduplication
            key = f"{lesson.category}:{lesson.agent}:{hash(lesson.observation) % 10000}"
            
            if key in self.kb.lessons:
                # Reinforce existing lesson
                existing = self.kb.lessons[key]
                existing.occurrences += 1
                existing.last_seen = now
                # Confidence increases with repetition (caps at 0.95)
                existing.confidence = min(0.95, existing.confidence + 0.05)
            else:
                # New lesson
                lesson.first_seen = now
                lesson.last_seen = now
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
        
        for key, lesson in self.kb.lessons.items():
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
        """Compare current trace metrics against historical best.
        
        Returns improvement/regression signal for key metrics.
        """
        from agentguard.analysis import analyze_failures, analyze_bottleneck
        
        current_f = analyze_failures(current_trace)
        current_bn = analyze_bottleneck(current_trace) if current_trace.agent_spans else None
        
        # Compare against knowledge base patterns
        historical_issues = len(self.kb.lessons)
        current_issues = len(self.reflect(current_trace).lessons)
        
        trend = "stable"
        if current_issues < historical_issues * 0.5:
            trend = "improving"
        elif current_issues > historical_issues * 1.5 and historical_issues > 0:
            trend = "degrading"
        
        return {
            "trend": trend,
            "current_issues": current_issues,
            "historical_avg_issues": historical_issues / max(self.kb.trace_count, 1),
            "resilience": current_f.resilience_score,
            "bottleneck": current_bn.bottleneck_span if current_bn else "N/A",
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
        trends = []
        
        for key, lesson in self.kb.lessons.items():
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
