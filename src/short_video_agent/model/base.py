"""Model adapter contract shared by live and mock implementations."""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import Field

from short_video_agent.schemas import (
    AgentDecision,
    BrandRule,
    DurationReport,
    Material,
    RuleReport,
    ScriptDraft,
    ScriptRequest,
    StrictModel,
    ToolResult,
)


class DecisionContext(StrictModel):
    request: ScriptRequest
    missing_fields: list[str] = Field(default_factory=list)
    applicable_rules: list[BrandRule] = Field(default_factory=list)
    retrieved_materials: list[Material] = Field(default_factory=list)
    draft: ScriptDraft | None = None
    duration_report: DurationReport | None = None
    rule_report: RuleReport | None = None
    last_observation: ToolResult | None = None
    query_history: list[dict[str, Any]] = Field(default_factory=list)
    remaining_model_steps: int = Field(ge=0)
    remaining_tool_calls: int = Field(ge=0)


class ModelAdapter(Protocol):
    mode: str

    def decide(self, context: DecisionContext) -> AgentDecision:
        """Select the next action from the current observable state."""

    @property
    def trace_metadata(self) -> dict[str, Any]:
        """Return non-secret runtime identity fields for trace provenance."""

    @property
    def last_response_id(self) -> str | None:
        """Return the provider response ID for the latest decision, if any."""

