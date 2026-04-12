"""Trace generator — generate synthetic traces for benchmarking and testing.

Create realistic random traces with configurable:
- Number of agents, tools, handoffs
- Failure rates
- Duration ranges
- Cost/token distributions
"""

from __future__ import annotations

import random
from typing import Optional

from agentguard.builder import TraceBuilder
from agentguard.core.trace import ExecutionTrace


_AGENT_NAMES = [
    "researcher", "analyst", "writer", "reviewer", "editor",
    "coder", "tester", "deployer", "monitor", "planner",
    "collector", "parser", "enricher", "summarizer", "validator",
]

_TOOL_NAMES = [
    "web_search", "db_query", "file_read", "api_call", "cache_lookup",
    "parser", "formatter", "validator", "notifier", "logger",
]


def generate_trace(
    task: str = "synthetic_pipeline",
    agents: int = 3,
    tools_per_agent: int = 1,
    handoffs: bool = True,
    failure_rate: float = 0.1,
    min_duration_ms: float = 500,
    max_duration_ms: float = 10000,
    include_llm_calls: bool = True,
    include_costs: bool = True,
    seed: Optional[int] = None,
) -> ExecutionTrace:
    """Generate a random but realistic trace.
    
    Args:
        task: Task description.
        agents: Number of agents in the pipeline.
        tools_per_agent: Average tools per agent.
        handoffs: Whether to add handoffs between agents.
        failure_rate: Probability of each span failing.
        min_duration_ms: Minimum span duration.
        max_duration_ms: Maximum span duration.
        include_llm_calls: Add LLM call spans.
        include_costs: Add token/cost tracking.
        seed: Random seed for reproducibility.
    
    Returns:
        A synthetic ExecutionTrace.
    """
    if seed is not None:
        random.seed(seed)
    
    builder = TraceBuilder(task)
    
    agent_names = random.sample(_AGENT_NAMES, min(agents, len(_AGENT_NAMES)))
    prev_agent = None
    
    for i, name in enumerate(agent_names):
        dur = random.uniform(min_duration_ms, max_duration_ms)
        failed = random.random() < failure_rate
        status = "failed" if failed else "completed"
        error = f"Random failure in {name}" if failed else None
        
        tokens = random.randint(500, 5000) if include_costs else None
        cost = tokens * 0.00003 if tokens else None  # ~$0.03/1K tokens
        
        output = {"result": f"output_from_{name}", "items": list(range(random.randint(1, 5)))}
        input_data = {"query": f"input_for_{name}"} if i > 0 else None
        
        # Add handoff from previous agent
        if handoffs and prev_agent:
            builder.handoff(prev_agent, name, context_size=random.randint(100, 5000))
        
        builder.agent(name, duration_ms=dur, status=status, error=error,
                     output_data=output, input_data=input_data,
                     token_count=tokens, cost_usd=cost)
        
        # Add tools
        num_tools = max(0, random.randint(0, tools_per_agent * 2))
        for j in range(num_tools):
            tool_name = random.choice(_TOOL_NAMES)
            tool_dur = random.uniform(100, dur / 2)
            tool_failed = random.random() < failure_rate * 0.5
            retry = random.randint(0, 2) if random.random() < 0.2 else 0
            builder.tool(f"{tool_name}", duration_ms=tool_dur,
                        status="failed" if tool_failed else "completed",
                        error=f"{tool_name} error" if tool_failed else None,
                        retry_count=retry)
        
        # Add LLM call
        if include_llm_calls and random.random() < 0.7:
            llm_dur = random.uniform(1000, dur * 0.8)
            llm_tokens = random.randint(500, 3000)
            builder.llm_call(f"llm_{name}", duration_ms=llm_dur,
                           token_count=llm_tokens,
                           cost_usd=llm_tokens * 0.00003)
        
        builder.end()
        prev_agent = name
    
    return builder.build()


def generate_batch(
    count: int = 10,
    **kwargs,
) -> list[ExecutionTrace]:
    """Generate multiple synthetic traces."""
    # Remove seed from kwargs before passing
    kwargs.pop("seed", None)
    return [generate_trace(task=f"synthetic_{i}", seed=i, **kwargs) 
            for i in range(count)]
