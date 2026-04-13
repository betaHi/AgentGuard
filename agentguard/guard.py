"""Guard mode — continuous monitoring with alert support.

Usage:
    from agentguard.guard import Guard

    guard = Guard(config_path="agentguard.yaml")
    guard.watch(interval=300)  # check every 5 min
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path

from agentguard.core.eval_schema import EvaluationResult, RuleVerdict
from agentguard.core.trace import ExecutionTrace
from agentguard.eval.rules import evaluate_rules


class AlertHandler:
    """Base class for alert handlers."""

    def send(self, message: str, severity: str = "warning", metadata: dict = None) -> None:
        raise NotImplementedError


class StdoutAlert(AlertHandler):
    """Print alerts to stdout."""

    def send(self, message: str, severity: str = "warning", metadata: dict = None) -> None:
        icon = "🔴" if severity == "critical" else "🟡" if severity == "warning" else "🟢"
        timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
        print(f"{icon} [{timestamp}] [{severity.upper()}] {message}")


class FileAlert(AlertHandler):
    """Write alerts to a file."""

    def __init__(self, filepath: str = ".agentguard/alerts.jsonl"):
        self.filepath = Path(filepath)

    def send(self, message: str, severity: str = "warning", metadata: dict = None) -> None:
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "severity": severity,
            "message": message,
            **(metadata or {}),
        }
        with self.filepath.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


class WebhookAlert(AlertHandler):
    """Send alerts via HTTP webhook."""

    def __init__(self, url: str):
        self.url = url

    def send(self, message: str, severity: str = "warning", metadata: dict = None) -> None:
        try:
            import urllib.request
            payload = json.dumps({
                "text": f"[{severity.upper()}] {message}",
                "severity": severity,
                **(metadata or {}),
            }).encode()
            req = urllib.request.Request(
                self.url, data=payload,
                headers={"Content-Type": "application/json"}
            )
            urllib.request.urlopen(req, timeout=10)
        except Exception as e:
            print(f"Webhook alert failed: {e}")


class Guard:
    """Continuous monitoring engine.

    Watches trace output directory for new traces,
    evaluates them against rules, and sends alerts on failures.
    """

    def __init__(
        self,
        traces_dir: str = ".agentguard/traces",
        rules: list[dict] | None = None,
        alert_handlers: list[AlertHandler] | None = None,
        fail_threshold: int = 3,
        auto_learn: bool = False,
    ):
        self.traces_dir = Path(traces_dir)
        self.rules = rules or []
        self.alert_handlers = alert_handlers or [StdoutAlert()]
        self.fail_threshold = fail_threshold
        self.auto_learn = auto_learn
        self._seen: set[str] = set()
        self._consecutive_fails: dict[str, int] = {}
        self._evolve_engine = None
        if auto_learn:
            from agentguard.evolve import EvolutionEngine
            self._evolve_engine = EvolutionEngine()

    def _alert(self, message: str, severity: str = "warning", metadata: dict = None) -> None:
        for handler in self.alert_handlers:
            try:
                handler.send(message, severity, metadata)
            except Exception as e:
                print(f"Alert handler error: {e}")

    def check_new_traces(self) -> list[EvaluationResult]:
        """Check for new traces and evaluate them."""
        if not self.traces_dir.exists():
            return []

        results = []
        for trace_file in sorted(self.traces_dir.glob("*.json")):
            if trace_file.name in self._seen:
                continue
            self._seen.add(trace_file.name)

            try:
                data = json.loads(trace_file.read_text(encoding="utf-8"))
                trace = ExecutionTrace.from_dict(data)

                # Check for failed spans — separate agent and tool failures
                failed_agents = [s for s in trace.agent_spans if s.status.value == "failed"]
                failed_tools = [s for s in trace.tool_spans if s.status.value == "failed"]
                all_failed = failed_agents + failed_tools

                if all_failed:
                    # Only track AGENT failures for consecutive failure escalation
                    for s in failed_agents:
                        self._consecutive_fails[s.name] = self._consecutive_fails.get(s.name, 0) + 1
                        if self._consecutive_fails[s.name] >= self.fail_threshold:
                            self._alert(
                                f"Agent '{s.name}' has failed {self._consecutive_fails[s.name]} consecutive times",
                                severity="critical",
                                metadata={"agent": s.name, "trace_id": trace.trace_id}
                            )

                    # Report tool failures as warnings (not escalated)
                    if failed_tools:
                        self._alert(
                            f"Trace {trace.trace_id} ({trace.task}): {len(failed_tools)} tool failures",
                            severity="warning",
                            metadata={"trace_id": trace.trace_id,
                                     "failed_tools": [s.name for s in failed_tools]}
                        )

                    if failed_agents:
                        self._alert(
                            f"Trace {trace.trace_id} ({trace.task}): {len(failed_agents)} agent failures",
                            severity="warning",
                            metadata={"trace_id": trace.trace_id,
                                     "failed_agents": [s.name for s in failed_agents]}
                        )
                else:
                    # Reset consecutive fail counters for successful agents
                    for s in trace.agent_spans:
                        self._consecutive_fails[s.name] = 0

                # Evaluate rules if configured
                if self.rules:
                    for span in trace.agent_spans:
                        if span.output_data:
                            rule_results = evaluate_rules(span.output_data, self.rules)
                            eval_result = EvaluationResult(
                                trace_id=trace.trace_id,
                                agent_name=span.name,
                                rules=rule_results,
                            )
                            results.append(eval_result)

                            if eval_result.overall_verdict == RuleVerdict.FAIL:
                                self._alert(
                                    f"Agent '{span.name}' failed {eval_result.failed}/{eval_result.total} rules",
                                    severity="warning",
                                    metadata={"agent": span.name, "trace_id": trace.trace_id}
                                )

                # Auto-learn from this trace
                if self._evolve_engine:
                    self._evolve_engine.learn(trace)

            except Exception as e:
                self._alert(f"Error processing {trace_file.name}: {e}", severity="warning")

        return results

    def watch(self, interval: int = 60, max_iterations: int | None = None) -> None:
        """Watch for new traces continuously.

        Args:
            interval: Seconds between checks.
            max_iterations: Stop after N iterations (None = infinite).
        """
        print(f"🛡️ AgentGuard watching {self.traces_dir} (every {interval}s)")
        iteration = 0
        try:
            while max_iterations is None or iteration < max_iterations:
                self.check_new_traces()
                iteration += 1
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\n🛡️ Guard stopped.")
