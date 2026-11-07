"""Allow-listed tool registry used by the future execution node."""

from __future__ import annotations

from typing import Any

from short_video_agent.errors import ToolExecutionError
from short_video_agent.schemas import ToolResult
from short_video_agent.tools.base import AgentTool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, AgentTool] = {}

    def register(self, tool: AgentTool) -> None:
        if tool.name in self._tools:
            raise ToolExecutionError(
                code="duplicate_tool",
                message=f"Tool '{tool.name}' is already registered.",
            )
        self._tools[tool.name] = tool

    def get(self, name: str) -> AgentTool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise ToolExecutionError(
                code="tool_not_registered",
                message=f"Tool '{name}' is not registered.",
            ) from exc

    def invoke(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        return self.get(name).invoke(arguments)

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._tools))

