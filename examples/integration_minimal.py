"""Minimal SDK integration example for an existing project."""

from __future__ import annotations

import agentguard
from agentguard import record_agent, record_tool
from agentguard.sdk.recorder import finish_recording, init_recorder


agentguard.configure(
    output_dir=".agentguard/traces",
    auto_thread_context=True,
)


@record_tool(name="search")
def search(query: str) -> list[dict[str, str]]:
    """Existing tool code can stay unchanged apart from the decorator."""
    return [{"title": f"Result for {query}", "url": "https://example.com"}]


@record_agent(name="researcher", version="v1")
def researcher(topic: str) -> dict[str, list[dict[str, str]]]:
    """Existing agent code can stay unchanged apart from the decorator."""
    return {"results": search(topic)}


def main() -> None:
    init_recorder(task="minimal integration")
    result = researcher("agent orchestration diagnostics")
    trace = finish_recording()

    print("AgentGuard Minimal Integration")
    print(f"Results: {len(result['results'])}")
    print(f"Trace: {trace.trace_id}")
    print(f"Saved to: .agentguard/traces/{trace.trace_id}.json")


if __name__ == "__main__":
    main()