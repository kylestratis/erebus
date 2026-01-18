"""Diagnostics module for tracking timing and metrics.

Provides context managers and data classes for collecting performance
metrics during request processing. Diagnostics are only logged when
LOG_LEVEL=DEBUG to avoid noise in production.

Usage:
    from bot.diagnostics import track_request, track_tool

    with track_request("chat") as metrics:
        # Do work...
        with track_tool(metrics, "vault_read_note"):
            # Execute tool...
        # Metrics logged automatically at end
"""

from __future__ import annotations

import logging
import time
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ToolCallMetrics:
    """Metrics for a single tool call.

    Attributes:
        tool_name: Name of the tool being called.
        start_time: Perf counter value at start.
        end_time: Perf counter value at end.
        success: Whether the tool call succeeded.
        error_message: Error message if the tool call failed.
    """

    tool_name: str
    start_time: float = field(default_factory=time.perf_counter)
    end_time: float | None = None
    success: bool = True
    error_message: str | None = None

    @property
    def elapsed_ms(self) -> float:
        """Elapsed time in milliseconds."""
        end = self.end_time or time.perf_counter()
        return (end - self.start_time) * 1000

    def finish(self, success: bool = True, error: str | None = None) -> None:
        """Mark the tool call as complete.

        Args:
            success: Whether the tool call succeeded.
            error: Error message if failed.
        """
        self.end_time = time.perf_counter()
        self.success = success
        self.error_message = error


@dataclass
class RequestMetrics:
    """Metrics collected during a request.

    Attributes:
        label: Human-readable label for this request.
        start_time: Perf counter value at start.
        end_time: Perf counter value at end.
        tool_calls: List of tool call metrics.
        metadata: Additional key-value metadata.
    """

    label: str = ""
    start_time: float = field(default_factory=time.perf_counter)
    end_time: float | None = None
    tool_calls: list[ToolCallMetrics] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def elapsed_ms(self) -> float:
        """Total elapsed time in milliseconds."""
        end = self.end_time or time.perf_counter()
        return (end - self.start_time) * 1000

    @property
    def total_tool_time_ms(self) -> float:
        """Total time spent in tool execution."""
        return sum(t.elapsed_ms for t in self.tool_calls)

    @property
    def successful_tools(self) -> int:
        """Number of successful tool calls."""
        return sum(1 for t in self.tool_calls if t.success)

    @property
    def failed_tools(self) -> int:
        """Number of failed tool calls."""
        return sum(1 for t in self.tool_calls if not t.success)

    def add_metadata(self, key: str, value: Any) -> None:
        """Add metadata to the request.

        Args:
            key: Metadata key.
            value: Metadata value.
        """
        self.metadata[key] = value

    def finish(self) -> None:
        """Mark the request as complete."""
        self.end_time = time.perf_counter()

    def log_summary(self) -> None:
        """Log a summary of the metrics if debug mode is enabled."""
        if not logger.isEnabledFor(logging.DEBUG):
            return

        # Build the main summary line
        parts = [f"total={self.elapsed_ms:.0f}ms"]

        if self.tool_calls:
            parts.append(
                f"tools={len(self.tool_calls)} ({self.total_tool_time_ms:.0f}ms)"
            )
            if self.failed_tools > 0:
                parts.append(f"failed={self.failed_tools}")

        # Add metadata
        for key, value in self.metadata.items():
            parts.append(f"{key}={value}")

        summary = ", ".join(parts)
        logger.debug(f"[DIAGNOSTICS] {self.label}: {summary}")

        # Log individual tool calls
        for tc in self.tool_calls:
            status = "ok" if tc.success else f"error: {tc.error_message or 'unknown'}"
            logger.debug(f"  - {tc.tool_name}: {tc.elapsed_ms:.0f}ms ({status})")


@contextmanager
def track_request(label: str) -> Generator[RequestMetrics, None, None]:
    """Context manager for tracking request metrics.

    Automatically logs a summary when the context exits (if DEBUG enabled).

    Args:
        label: A label for this request (e.g., "chat", "daily workflow").

    Yields:
        RequestMetrics instance for collecting metrics.

    Example:
        with track_request("chat") as metrics:
            metrics.add_metadata("user_id", 12345)
            response = await eidolon.chat(...)
    """
    metrics = RequestMetrics(label=label)
    try:
        yield metrics
    finally:
        metrics.finish()
        metrics.log_summary()


@contextmanager
def track_tool(
    metrics: RequestMetrics, tool_name: str
) -> Generator[ToolCallMetrics, None, None]:
    """Context manager for tracking tool call metrics.

    Args:
        metrics: The parent RequestMetrics to add this tool call to.
        tool_name: The name of the tool being called.

    Yields:
        ToolCallMetrics instance for this tool call.

    Example:
        with track_request("chat") as metrics:
            with track_tool(metrics, "vault_read_note") as tool_metrics:
                result = await vault.read_note(...)
    """
    tool_metrics = ToolCallMetrics(tool_name=tool_name)
    metrics.tool_calls.append(tool_metrics)
    try:
        yield tool_metrics
    except Exception as e:
        tool_metrics.finish(success=False, error=str(e))
        raise
    else:
        tool_metrics.finish(success=True)


def format_duration(ms: float) -> str:
    """Format a duration in milliseconds to a human-readable string.

    Args:
        ms: Duration in milliseconds.

    Returns:
        Formatted string like "1.2s" or "150ms".
    """
    if ms >= 1000:
        return f"{ms / 1000:.1f}s"
    return f"{ms:.0f}ms"
