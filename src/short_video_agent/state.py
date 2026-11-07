"""LangGraph state contract.

The graph implementation is intentionally deferred to the core ReAct stage.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from short_video_agent.schemas import (
    AgentDecision,
    AgentResult,
    BrandRule,
    DurationReport,
    Material,
    RuleReport,
    ScriptDraft,
    ScriptRequest,
    TaskStatus,
    TerminalReason,
    ToolResult,
    TraceEvent,
)


class AgentState(TypedDict, total=False):
    request: ScriptRequest
    missing_fields: list[str]
    applicable_rules: list[BrandRule]
    query_history: Annotated[list[dict[str, Any]], operator.add]
    retrieved_materials: list[Material]
    draft: ScriptDraft | None
    duration_report: DurationReport | None
    rule_report: RuleReport | None
    last_observation: ToolResult | None
    pending_decision: AgentDecision | None
    pending_tool_result: ToolResult | None
    pending_tool_args: dict[str, Any] | None
    model_step_count: int
    tool_call_count: int
    invalid_decision_count: int
    status: TaskStatus
    risks: Annotated[list[str], operator.add]
    terminal_reason: TerminalReason | None
    terminal_message: str | None
    requested_fields: list[str]
    requested_details: str | None
    trace_events: Annotated[list[TraceEvent], operator.add]
    result: AgentResult | None

