"""Plugin system — register custom analyzers and exporters.

Allows users to extend AgentGuard with custom:
- Analyzers (custom analysis on traces)
- Exporters (custom output formats)
- Rules (custom alert rules)
- Hooks (custom span lifecycle callbacks)
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from agentguard.core.trace import ExecutionTrace

# Type aliases
Analyzer = Callable[[ExecutionTrace], dict]
Exporter = Callable[[ExecutionTrace], str]


@dataclass
class PluginInfo:
    """Metadata about a registered plugin."""
    name: str
    version: str
    author: str
    description: str
    plugin_type: str  # "analyzer", "exporter", "rule"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "author": self.author,
            "description": self.description,
            "type": self.plugin_type,
        }


class PluginRegistry:
    """Central registry for AgentGuard plugins."""

    def __init__(self) -> None:
        self._analyzers: dict[str, tuple[PluginInfo, Analyzer]] = {}
        self._exporters: dict[str, tuple[PluginInfo, Exporter]] = {}

    def register_analyzer(
        self,
        name: str,
        fn: Analyzer,
        version: str = "0.1.0",
        author: str = "unknown",
        description: str = "",
    ) -> None:
        """Register a custom analyzer."""
        info = PluginInfo(name=name, version=version, author=author,
                         description=description, plugin_type="analyzer")
        self._analyzers[name] = (info, fn)

    def register_exporter(
        self,
        name: str,
        fn: Exporter,
        version: str = "0.1.0",
        author: str = "unknown",
        description: str = "",
    ) -> None:
        """Register a custom exporter."""
        info = PluginInfo(name=name, version=version, author=author,
                         description=description, plugin_type="exporter")
        self._exporters[name] = (info, fn)

    def run_analyzer(self, name: str, trace: ExecutionTrace) -> dict:
        """Run a registered analyzer."""
        if name not in self._analyzers:
            raise KeyError(f"Analyzer '{name}' not registered")
        _, fn = self._analyzers[name]
        return fn(trace)

    def run_exporter(self, name: str, trace: ExecutionTrace) -> str:
        """Run a registered exporter."""
        if name not in self._exporters:
            raise KeyError(f"Exporter '{name}' not registered")
        _, fn = self._exporters[name]
        return fn(trace)

    def run_all_analyzers(self, trace: ExecutionTrace) -> dict:
        """Run all registered analyzers."""
        results = {}
        for name, (_info, fn) in self._analyzers.items():
            try:
                results[name] = fn(trace)
            except Exception as e:
                results[name] = {"error": str(e)}
        return results

    def list_plugins(self) -> list[PluginInfo]:
        """List all registered plugins."""
        plugins = []
        for info, _ in self._analyzers.values():
            plugins.append(info)
        for info, _ in self._exporters.values():
            plugins.append(info)
        return plugins

    @property
    def plugin_count(self) -> int:
        return len(self._analyzers) + len(self._exporters)


# Global registry
_global_registry = PluginRegistry()


def get_plugin_registry() -> PluginRegistry:
    """Get the global plugin registry."""
    return _global_registry


def register_analyzer(name: str, fn: Analyzer, **kwargs) -> None:
    """Convenience: register analyzer in global registry."""
    _global_registry.register_analyzer(name, fn, **kwargs)


def register_exporter(name: str, fn: Exporter, **kwargs) -> None:
    """Convenience: register exporter in global registry."""
    _global_registry.register_exporter(name, fn, **kwargs)
