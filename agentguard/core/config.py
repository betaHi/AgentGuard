"""Agent configuration and versioning.

Supports loading config from JSON (zero dependencies) or YAML (requires PyYAML).

- JSON path: agentguard.json — zero external dependencies
- YAML path: agentguard.yaml — requires `pip install agentguard[yaml]`
- Python dict: GuardConfig.from_dict() — always available
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class AgentTestConfig:
    """Test definition for an agent."""
    name: str = ""
    input_data: Any = None
    assertions: list[dict] = field(default_factory=list)


@dataclass
class AgentConfig:
    """Configuration for a single agent."""
    name: str = ""
    version: str = "latest"
    description: str = ""
    tests: list[AgentTestConfig] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def config_hash(self) -> str:
        """Compute a hash of the config for version tracking."""
        content = json.dumps({
            "name": self.name, "version": self.version,
            "tests": [{"name": t.name, "assertions": t.assertions} for t in self.tests],
            "metadata": self.metadata,
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:12]


@dataclass
class GuardConfig:
    """Top-level AgentGuard configuration."""
    agents: list[AgentConfig] = field(default_factory=list)
    output_dir: str = ".agentguard"

    @classmethod
    def from_dict(cls, data: dict) -> GuardConfig:
        """Load config from a dictionary.

        Args:
            data: Configuration dictionary.

        Returns:
            AgentGuardConfig instance.
        """
        agents = []
        for agent_data in data.get("agents", []):
            tests = []
            for test_data in agent_data.get("tests", []):
                tests.append(AgentTestConfig(
                    name=test_data.get("name", ""),
                    input_data=test_data.get("input"),
                    assertions=test_data.get("assertions", []),
                ))
            agents.append(AgentConfig(
                name=agent_data.get("name", ""),
                version=agent_data.get("version", "latest"),
                description=agent_data.get("description", ""),
                tests=tests,
                metadata=agent_data.get("metadata", {}),
            ))
        return cls(agents=agents, output_dir=data.get("output_dir", ".agentguard"))

    @classmethod
    def from_file(cls, filepath: str = "agentguard.yaml") -> GuardConfig:
        """Load config from a YAML or JSON file.

        Args:
            path: Path to JSON configuration file.

        Returns:
            AgentGuardConfig instance loaded from file.
        """
        path = Path(filepath)
        if not path.exists():
            return cls()

        content = path.read_text(encoding="utf-8")

        if filepath.endswith(".json"):
            return cls.from_dict(json.loads(content))

        # Simple YAML parser (handles basic nested structures)
        # For full YAML support, users can install PyYAML
        try:
            import yaml
            return cls.from_dict(yaml.safe_load(content))
        except ImportError:
            # Fallback: try JSON-style parsing
            # If user needs YAML, they install pyyaml
            raise ImportError(
                "PyYAML is required for .yaml config files. "
                "Install with: pip install pyyaml\n"
                "Or use agentguard.json instead."
            ) from None
