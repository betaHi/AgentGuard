import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Demo: Async multi-agent workflow with AgentGuard tracing."""

import asyncio
from agentguard import record_agent_async, record_tool_async
from agentguard.sdk.recorder import init_recorder, finish_recording


@record_tool_async(name="async_search")
async def search(query: str) -> list[dict]:
    await asyncio.sleep(0.1)  # simulate API call
    return [{"title": f"Result: {query}", "url": "https://example.com"}]


@record_tool_async(name="async_summarize")
async def summarize(data: list) -> str:
    await asyncio.sleep(0.1)
    return f"Summary of {len(data)} items"


@record_agent_async(name="async-researcher", version="v1.0")
async def researcher(topic: str) -> dict:
    results = await search(topic)
    summary = await summarize(results)
    return {"results": results, "summary": summary}


@record_agent_async(name="async-coordinator", version="v1.0")
async def coordinator(task: str) -> dict:
    # Run multiple agents concurrently
    results = await asyncio.gather(
        researcher(f"{task} - part 1"),
        researcher(f"{task} - part 2"),
    )
    return {"task": task, "agent_results": results}


async def main():
    init_recorder(task="Async Research Demo", trigger="manual")
    result = await coordinator("AI Agent Observability")
    trace = finish_recording()
    print(f"✅ Trace: .agentguard/traces/{trace.trace_id}.json")
    print(f"   Spans: {len(trace.spans)}, Duration: {trace.duration_ms:.0f}ms")


if __name__ == "__main__":
    asyncio.run(main())
