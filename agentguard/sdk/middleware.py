"""Middleware utilities for framework integration.

Provides utilities to instrument existing code without modifying it,
useful when integrating with third-party agent frameworks.

Usage:
    # Wrap any callable
    from agentguard.sdk.middleware import wrap_agent, wrap_tool
    
    original_agent = some_framework.Agent(...)
    traced_agent = wrap_agent(original_agent.run, name="my-agent", version="v1")
    traced_agent(task)
    
    # Or patch a class method
    from agentguard.sdk.middleware import patch_method
    patch_method(MyAgent, "run", agent_name="my-agent", version="v1")
"""

from __future__ import annotations

import functools
from typing import Any, Callable, Optional, Type

from agentguard.sdk.decorators import record_agent, record_tool


def wrap_agent(
    fn: Callable,
    name: str,
    version: str = "latest",
    metadata: Optional[dict] = None,
) -> Callable:
    """Wrap any callable to record it as an agent span.
    
    This is non-intrusive: the original function is not modified.
    
    Args:
        fn: Function to wrap.
        name: Agent name.
        version: Agent version.
        metadata: Additional metadata.
    
    Returns:
        Wrapped function.
    
    Example:
        traced_fn = wrap_agent(my_fn, name="agent", version="v1")
        traced_fn(args)
    """
    decorator = record_agent(name=name, version=version, metadata=metadata)
    return decorator(fn)


def wrap_tool(
    fn: Callable,
    name: str,
    metadata: Optional[dict] = None,
) -> Callable:
    """Wrap any callable to record it as a tool span.
    
    Args:
        fn: Function to wrap.
        name: Tool name.
        metadata: Additional metadata.
    
    Returns:
        Wrapped function.
    """
    decorator = record_tool(name=name, metadata=metadata)
    return decorator(fn)


def patch_method(
    cls: Type,
    method_name: str,
    agent_name: Optional[str] = None,
    tool_name: Optional[str] = None,
    version: str = "latest",
) -> None:
    """Monkey-patch a class method to add tracing.
    
    Modifies the class in-place. Use with caution.
    
    Args:
        cls: Class to patch.
        method_name: Name of the method to patch.
        agent_name: If set, records as an agent span.
        tool_name: If set, records as a tool span.
        version: Version string (for agent spans).
    
    Example:
        class MyAgent:
            def run(self, task): ...
        
        patch_method(MyAgent, "run", agent_name="my-agent", version="v1")
        # Now MyAgent().run(task) is automatically traced
    """
    original = getattr(cls, method_name)
    
    if agent_name:
        wrapped = wrap_agent(original, name=agent_name, version=version)
    elif tool_name:
        wrapped = wrap_tool(original, name=tool_name)
    else:
        raise ValueError("Either agent_name or tool_name must be provided")
    
    setattr(cls, method_name, wrapped)
