"""High-level wiring for Claude SDK live runtime capture."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from agentguard.core.trace import ExecutionTrace
from agentguard.runtime.claude.adapter import ClaudeRuntimeAdapter


class AgentGuardClaudeClient:
    """Thin proxy that captures Claude runtime activity into a trace."""

    def __init__(self, client: Any) -> None:
        self._client = client
        self._adapter = ClaudeRuntimeAdapter(client)

    async def __aenter__(self) -> AgentGuardClaudeClient:
        """Enter the wrapped Claude client context."""
        await self._client.__aenter__()
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> Any:
        """Exit the wrapped Claude client context."""
        return await self._client.__aexit__(exc_type, exc, tb)

    def __getattr__(self, name: str) -> Any:
        """Delegate all unknown attributes to the wrapped client."""
        return getattr(self._client, name)

    async def query(self, prompt: Any, session_id: str = "default") -> None:
        """Start live capture for the next Claude query."""
        self._adapter.install_hooks()
        self._adapter.start_query(prompt, session_id)
        await self._client.query(prompt, session_id=session_id)

    async def receive_messages(self) -> AsyncIterator[Any]:
        """Yield Claude messages while ingesting them into AgentGuard."""
        async for message in self._client.receive_messages():
            self._adapter.ingest_message(message)
            yield message

    async def receive_response(self) -> AsyncIterator[Any]:
        """Yield Claude response messages while ingesting them into AgentGuard."""
        async for message in self._client.receive_response():
            self._adapter.ingest_message(message)
            yield message

    def agentguard_trace(self) -> ExecutionTrace | None:
        """Return the trace accumulated for the most recent Claude run."""
        return self._adapter.current_trace()


def wrap_claude_client(client: Any) -> AgentGuardClaudeClient:
    """Wrap a Claude SDK client so live activity becomes an AgentGuard trace."""
    return AgentGuardClaudeClient(client)