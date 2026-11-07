"""Business tool protocol."""

from __future__ import annotations

from typing import Any, Protocol

from short_video_agent.schemas import ToolResult


class AgentTool(Protocol):
    name: str

    def invoke(self, arguments: dict[str, Any]) -> ToolResult:
        """Execute one allow-listed local business operation."""

