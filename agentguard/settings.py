"""Global runtime settings for AgentGuard.

Provides a single ``configure()`` entry point for users to set global
behavior without touching individual modules. Settings are stored in a
module-level singleton and read by other components.

Usage:
    import agentguard
    agentguard.configure(
        output_dir="./traces",
        max_trace_size_mb=20,
        sampling_rate=0.5,
    )

Why a singleton: AgentGuard is observability tooling — there should be
exactly one global config per process, matching how logging.basicConfig works.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

_logger = logging.getLogger(__name__)


@dataclass
class Settings:
    """Global AgentGuard runtime settings.

    Attributes:
        output_dir: Directory for trace output files.
        max_trace_size_mb: Warn/truncate threshold in megabytes.
        sampling_rate: Fraction of traces to record (0.0–1.0).
            1.0 records everything; 0.1 records ~10%.
        auto_truncate: If True, automatically truncate oversized traces.
        auto_thread_context: If True, standard threads inherit trace context.
        log_level: Logging level for AgentGuard internal logs.
    """
    output_dir: str = ".agentguard/traces"
    max_trace_size_mb: float = 10.0
    sampling_rate: float = 1.0
    auto_truncate: bool = False
    auto_thread_context: bool = False
    log_level: str = "WARNING"

    def validate(self) -> list[str]:
        """Validate settings, returning a list of error messages.

        Returns:
            Empty list if valid, otherwise list of error strings.
        """
        errors: list[str] = []
        if not 0.0 <= self.sampling_rate <= 1.0:
            errors.append(
                f"sampling_rate must be 0.0–1.0, got {self.sampling_rate}"
            )
        if self.max_trace_size_mb <= 0:
            errors.append(
                f"max_trace_size_mb must be > 0, got {self.max_trace_size_mb}"
            )
        return errors


# Module-level singleton
_settings = Settings()


def configure(
    output_dir: str | None = None,
    max_trace_size_mb: float | None = None,
    sampling_rate: float | None = None,
    auto_truncate: bool | None = None,
    auto_thread_context: bool | None = None,
    log_level: str | None = None,
) -> None:
    """Configure global AgentGuard settings.

    Only provided arguments are updated; others keep their current value.
    Invalid settings raise ValueError immediately.

    Args:
        output_dir: Directory for trace output files.
        max_trace_size_mb: Size warning/truncation threshold (default 10).
        sampling_rate: Fraction of traces to record, 0.0–1.0 (default 1.0).
        auto_truncate: Auto-truncate oversized traces on serialization.
        auto_thread_context: Propagate trace context into standard threads.
        log_level: Logging level for AgentGuard internals.

    Raises:
        ValueError: If any setting is invalid.
    """
    global _settings
    if output_dir is not None:
        _settings.output_dir = output_dir
    if max_trace_size_mb is not None:
        _settings.max_trace_size_mb = max_trace_size_mb
    if sampling_rate is not None:
        _settings.sampling_rate = sampling_rate
    if auto_truncate is not None:
        _settings.auto_truncate = auto_truncate
    if auto_thread_context is not None:
        _settings.auto_thread_context = auto_thread_context
    if log_level is not None:
        _settings.log_level = log_level
        logging.getLogger("agentguard").setLevel(log_level)

    errors = _settings.validate()
    if errors:
        raise ValueError(f"Invalid settings: {'; '.join(errors)}")

    from agentguard.sdk.threading import (
        disable_auto_trace_threading,
        enable_auto_trace_threading,
    )

    if _settings.auto_thread_context:
        enable_auto_trace_threading()
    else:
        disable_auto_trace_threading()

    _logger.info("AgentGuard configured: %s", _settings)


def get_settings() -> Settings:
    """Get the current global settings (read-only reference).

    Returns:
        The current Settings singleton.
    """
    return _settings


def reset_settings() -> None:
    """Reset all settings to defaults. Primarily for testing."""
    global _settings
    from agentguard.sdk.threading import disable_auto_trace_threading

    _settings = Settings()
    disable_auto_trace_threading()
