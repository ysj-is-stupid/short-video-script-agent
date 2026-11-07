"""Runtime composition for model, tools and the compiled LangGraph."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from short_video_agent.config import AppConfig
from short_video_agent.graph import build_graph
from short_video_agent.model.base import ModelAdapter
from short_video_agent.schemas import (
    AgentResult,
    BrandRule,
    Material,
    ScriptRequest,
    TaskStatus,
    TraceEvent,
    ResultKind,
    ToolResult,
)
from short_video_agent.state import AgentState
from short_video_agent.tools import (
    DurationEstimatorTool,
    MaterialSearchTool,
    RuleCheckerTool,
    ToolRegistry,
)


@dataclass(slots=True)
class RunOutcome:
    result: AgentResult
    trace_events: list[TraceEvent]
    final_state: AgentState


class FaultInjectingTool:
    """Deterministic acceptance-test wrapper around a real business tool."""

    def __init__(self, tool: Any, fault: str | None = None) -> None:
        self.name = tool.name
        self._tool = tool
        self._fault = fault

    def invoke(self, arguments: dict[str, Any]) -> ToolResult:
        if self._fault == "error":
            return ToolResult(
                tool_name=self.name,
                call_id=f"fault-{uuid4().hex[:8]}",
                ok=False,
                result_kind=ResultKind.ERROR,
                summary=f"Injected {self.name} failure for acceptance verification.",
                error_code=f"injected_{self.name}_failure",
                retryable=False,
            )
        if self._fault == "timeout":
            return ToolResult(
                tool_name=self.name,
                call_id=f"fault-{uuid4().hex[:8]}",
                ok=False,
                result_kind=ResultKind.TIMEOUT,
                summary=f"Injected {self.name} timeout for acceptance verification.",
                error_code=f"injected_{self.name}_timeout",
                retryable=False,
            )
        if self._fault == "exception":
            raise RuntimeError(f"injected {self.name} exception")
        return self._tool.invoke(arguments)


def build_default_registry(
    materials: list[Material],
    *,
    search_failures_before_success: int = 0,
    duration_fault: str | None = None,
    rule_fault: str | None = None,
) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        MaterialSearchTool(
            materials,
            failures_before_success=search_failures_before_success,
        )
    )
    registry.register(FaultInjectingTool(DurationEstimatorTool(), duration_fault))
    registry.register(FaultInjectingTool(RuleCheckerTool(materials), rule_fault))
    return registry


def run_agent(
    *,
    request: ScriptRequest,
    materials: list[Material],
    rules: list[BrandRule],
    model_adapter: ModelAdapter,
    config: AppConfig,
    search_failures_before_success: int = 0,
    duration_fault: str | None = None,
    rule_fault: str | None = None,
) -> RunOutcome:
    registry = build_default_registry(
        materials,
        search_failures_before_success=search_failures_before_success,
        duration_fault=duration_fault,
        rule_fault=rule_fault,
    )
    graph = build_graph(
        model_adapter=model_adapter,
        tool_registry=registry,
        materials=materials,
        config=config,
    )
    initial_state: AgentState = {
        "request": request,
        "missing_fields": [],
        "applicable_rules": rules,
        "query_history": [],
        "retrieved_materials": [],
        "draft": None,
        "duration_report": None,
        "rule_report": None,
        "last_observation": None,
        "pending_decision": None,
        "pending_tool_result": None,
        "pending_tool_args": None,
        "model_step_count": 0,
        "tool_call_count": 0,
        "invalid_decision_count": 0,
        "status": TaskStatus.RUNNING,
        "risks": [],
        "terminal_reason": None,
        "terminal_message": None,
        "requested_fields": [],
        "requested_details": None,
        "trace_events": [],
        "result": None,
    }
    recursion_limit = 20 + (config.max_model_steps + config.max_tool_calls) * 8
    final_state = graph.invoke(
        initial_state,
        config={"recursion_limit": recursion_limit},
    )
    result = final_state.get("result")
    if result is None:
        raise RuntimeError("Agent graph ended without an AgentResult.")
    return RunOutcome(
        result=result,
        trace_events=final_state.get("trace_events", []),
        final_state=final_state,
    )
