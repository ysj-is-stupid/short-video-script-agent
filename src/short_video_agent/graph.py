"""Explicit LangGraph ReAct loop and completion guard."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from short_video_agent.config import AppConfig
from short_video_agent.drafting import canonicalize_draft
from short_video_agent.errors import (
    ModelAdapterError,
    ModelOutputValidationError,
    ToolExecutionError,
)
from short_video_agent.model.base import DecisionContext, ModelAdapter
from short_video_agent.schemas import (
    AgentDecision,
    AgentResult,
    DecisionAction,
    DurationReport,
    Material,
    ResultKind,
    RuleReport,
    Scene,
    TaskStatus,
    TerminalReason,
    ToolResult,
    TraceEvent,
)
from short_video_agent.state import AgentState
from short_video_agent.tools.registry import ToolRegistry


TOOL_ACTIONS = {
    DecisionAction.SEARCH_MATERIALS,
    DecisionAction.ESTIMATE_DURATION,
    DecisionAction.CHECK_RULES,
}


def _trace_event(
    state: AgentState,
    *,
    node: str,
    event_type: str,
    action: DecisionAction | None = None,
    public_reason: str | None = None,
    tool_name: str | None = None,
    proposed_tool_args: dict[str, Any] | None = None,
    executed_tool_args: dict[str, Any] | None = None,
    model_response_id: str | None = None,
    model_step: int | None = None,
    result_kind: ResultKind | None = None,
    result_summary: str | None = None,
    draft_revision: int | None = None,
    based_on_observation_id: str | None = None,
    status_after: TaskStatus | None = None,
) -> TraceEvent:
    sequence = len(state.get("trace_events", [])) + 1
    return TraceEvent(
        event_id=f"E{sequence:03d}-{uuid4().hex[:6]}",
        sequence=sequence,
        timestamp=datetime.now(timezone.utc),
        node=node,
        event_type=event_type,
        model_step=(
            state.get("model_step_count", 0) if model_step is None else model_step
        ),
        tool_call_count=state.get("tool_call_count", 0),
        action=action,
        public_reason=public_reason,
        tool_name=tool_name,
        proposed_tool_args=proposed_tool_args or {},
        executed_tool_args=executed_tool_args or {},
        model_response_id=model_response_id,
        result_kind=result_kind,
        result_summary=result_summary,
        draft_revision=draft_revision,
        status_after=status_after or state.get("status", TaskStatus.RUNNING),
        based_on_observation_id=based_on_observation_id,
    )


def _normalize_search_arguments(raw: dict[str, Any]) -> dict[str, Any]:
    """Reduce a model proposal to the exact allow-listed search parameters."""

    raw_scope_ids = raw.get("scope_ids", [])
    scope_ids = (
        [str(item) for item in raw_scope_ids]
        if isinstance(raw_scope_ids, list)
        else []
    )
    try:
        limit = max(1, min(int(raw.get("limit", 5)), 20))
    except (TypeError, ValueError):
        limit = 5
    return {
        "query": str(raw.get("query", "")).strip(),
        "product_name": str(raw.get("product_name") or "").strip(),
        "scope_ids": scope_ids,
        "limit": limit,
    }


def _last_response_id(model_adapter: ModelAdapter) -> str | None:
    value = getattr(model_adapter, "last_response_id", None)
    return str(value) if value else None


def _validate_decision(decision: AgentDecision, state: AgentState) -> None:
    if decision.action is DecisionAction.SEARCH_MATERIALS:
        if not str(decision.tool_args.get("query", "")).strip():
            raise ValueError("search_materials requires a non-empty query.")
    if decision.action in {
        DecisionAction.ESTIMATE_DURATION,
        DecisionAction.CHECK_RULES,
    } and decision.draft is None and state.get("draft") is None:
        raise ValueError(f"{decision.action.value} requires a script draft.")
    if decision.action is DecisionAction.REQUEST_INPUT and not decision.requested_fields:
        raise ValueError("request_input requires requested_fields.")

    if decision.draft is not None and state.get("draft") is not None:
        current = canonicalize_draft(state["draft"])
        proposed = canonicalize_draft(decision.draft)
        if proposed.revision <= current.revision:
            raise ValueError("Every submitted draft must increment its revision.")


def build_graph(
    *,
    model_adapter: ModelAdapter,
    tool_registry: ToolRegistry,
    materials: list[Material],
    config: AppConfig,
) -> Any:
    """Compile the explicit Agent loop with dependencies captured by closure."""

    material_by_id = {item.material_id: item for item in materials}

    def prepare_context(state: AgentState) -> dict[str, Any]:
        request = state["request"]
        missing = request.missing_required_fields
        observation = ToolResult(
            tool_name="prepare_context",
            call_id=f"input-{uuid4().hex[:8]}",
            ok=True,
            result_kind=ResultKind.EMPTY if missing else ResultKind.SUCCESS,
            summary=(
                f"Missing required fields: {', '.join(missing)}."
                if missing
                else "Request fields are complete."
            ),
            data={"missing_fields": missing},
        )
        event = _trace_event(
            state,
            node="prepare_context",
            event_type="observation",
            tool_name="prepare_context",
            result_kind=observation.result_kind,
            result_summary=observation.summary,
        )
        return {
            "missing_fields": missing,
            "last_observation": observation,
            "status": TaskStatus.RUNNING,
            "trace_events": [event],
        }

    def budget_before_model(state: AgentState) -> dict[str, Any]:
        if state.get("status") is not TaskStatus.RUNNING:
            return {}
        if state.get("model_step_count", 0) >= config.max_model_steps:
            return {
                "status": TaskStatus.INCOMPLETE,
                "terminal_reason": TerminalReason.MODEL_STEP_LIMIT_REACHED,
                "terminal_message": "已达到模型决策步数上限，任务未完成。",
            }
        return {}

    def budget_before_tool(state: AgentState) -> dict[str, Any]:
        if state.get("status") is not TaskStatus.RUNNING:
            return {}
        if state.get("tool_call_count", 0) >= config.max_tool_calls:
            return {
                "status": TaskStatus.INCOMPLETE,
                "terminal_reason": TerminalReason.TOOL_CALL_LIMIT_REACHED,
                "terminal_message": "已达到工具调用次数上限，任务未完成。",
            }
        return {}

    def agent_decide(state: AgentState) -> dict[str, Any]:
        context = DecisionContext(
            request=state["request"],
            missing_fields=state.get("missing_fields", []),
            applicable_rules=state.get("applicable_rules", []),
            retrieved_materials=state.get("retrieved_materials", []),
            draft=state.get("draft"),
            duration_report=state.get("duration_report"),
            rule_report=state.get("rule_report"),
            last_observation=state.get("last_observation"),
            query_history=state.get("query_history", []),
            remaining_model_steps=max(
                0, config.max_model_steps - state.get("model_step_count", 0)
            ),
            remaining_tool_calls=max(
                0, config.max_tool_calls - state.get("tool_call_count", 0)
            ),
        )
        new_step_count = state.get("model_step_count", 0) + 1
        try:
            decision = model_adapter.decide(context)
            _validate_decision(decision, state)
        except ModelOutputValidationError as exc:
            invalid_count = state.get("invalid_decision_count", 0) + 1
            observation = ToolResult(
                tool_name="model_decision",
                call_id=f"model-invalid-{uuid4().hex[:8]}",
                ok=False,
                result_kind=ResultKind.ERROR,
                summary=f"Invalid model decision: {exc.message}",
                error_code=exc.code,
                retryable=exc.retryable,
            )
            failed = invalid_count >= config.max_invalid_decisions
            status = TaskStatus.FAILED if failed else TaskStatus.RUNNING
            event = _trace_event(
                state,
                node="agent_decide",
                event_type="decision_error",
                tool_name="model_decision",
                result_kind=ResultKind.ERROR,
                result_summary=observation.summary,
                status_after=status,
                model_step=new_step_count,
                model_response_id=_last_response_id(model_adapter),
            )
            return {
                "model_step_count": new_step_count,
                "invalid_decision_count": invalid_count,
                "last_observation": observation,
                "pending_decision": None,
                "status": status,
                "terminal_reason": (
                    TerminalReason.MODEL_OUTPUT_INVALID if failed else None
                ),
                "terminal_message": (
                    "模型连续返回无效动作，任务失败。" if failed else None
                ),
                "trace_events": [event],
            }
        except ModelAdapterError as exc:
            invalid_count = state.get("invalid_decision_count", 0)
            retryable = exc.retryable
            observation = ToolResult(
                tool_name="model_decision",
                call_id=f"model-error-{uuid4().hex[:8]}",
                ok=False,
                result_kind=ResultKind.ERROR,
                summary=f"Model request failed: {exc}",
                error_code=exc.code,
                retryable=retryable,
            )
            failed = not retryable
            status = TaskStatus.FAILED if failed else TaskStatus.RUNNING
            event = _trace_event(
                state,
                node="agent_decide",
                event_type="model_request_error",
                tool_name="model_decision",
                result_kind=ResultKind.ERROR,
                result_summary=observation.summary,
                status_after=status,
                model_step=new_step_count,
                model_response_id=_last_response_id(model_adapter),
            )
            return {
                "model_step_count": new_step_count,
                "invalid_decision_count": invalid_count,
                "last_observation": observation,
                "pending_decision": None,
                "status": status,
                "terminal_reason": (
                    TerminalReason.INTERNAL_ERROR if failed else None
                ),
                "terminal_message": (
                    "模型请求发生不可重试错误，任务失败。" if failed else None
                ),
                "trace_events": [event],
            }
        except ValueError as exc:
            invalid_count = state.get("invalid_decision_count", 0) + 1
            observation = ToolResult(
                tool_name="model_decision",
                call_id=f"model-invalid-{uuid4().hex[:8]}",
                ok=False,
                result_kind=ResultKind.ERROR,
                summary=f"Invalid model decision: {exc}",
                error_code="invalid_model_decision",
                retryable=True,
            )
            failed = invalid_count >= config.max_invalid_decisions
            status = TaskStatus.FAILED if failed else TaskStatus.RUNNING
            event = _trace_event(
                state,
                node="agent_decide",
                event_type="decision_error",
                tool_name="model_decision",
                result_kind=ResultKind.ERROR,
                result_summary=observation.summary,
                status_after=status,
                model_step=new_step_count,
                model_response_id=_last_response_id(model_adapter),
            )
            return {
                "model_step_count": new_step_count,
                "invalid_decision_count": invalid_count,
                "last_observation": observation,
                "pending_decision": None,
                "status": status,
                "terminal_reason": (
                    TerminalReason.MODEL_OUTPUT_INVALID if failed else None
                ),
                "terminal_message": (
                    "模型连续返回无效动作，任务失败。" if failed else None
                ),
                "trace_events": [event],
            }

        event = _trace_event(
            state,
            node="agent_decide",
            event_type="decision",
            action=decision.action,
            public_reason=decision.public_reason,
            proposed_tool_args=decision.tool_args,
            model_response_id=_last_response_id(model_adapter),
            model_step=new_step_count,
            draft_revision=decision.draft.revision if decision.draft else None,
            based_on_observation_id=decision.based_on_observation_id,
        )
        return {
            "model_step_count": new_step_count,
            "pending_decision": decision,
            "trace_events": [event],
        }

    def apply_decision(state: AgentState) -> dict[str, Any]:
        decision = state["pending_decision"]
        if decision is None:
            return {}
        updates: dict[str, Any] = {}
        if decision.draft is not None:
            draft = canonicalize_draft(decision.draft)
            current = state.get("draft")
            current_fingerprint = (
                canonicalize_draft(current).fingerprint if current is not None else None
            )
            updates["draft"] = draft
            if draft.fingerprint != current_fingerprint:
                updates["duration_report"] = None
                updates["rule_report"] = None

        if decision.action is DecisionAction.REQUEST_INPUT:
            reason = (
                TerminalReason.MISSING_REQUIRED_FIELDS
                if state.get("missing_fields")
                else TerminalReason.NO_SUPPORTING_MATERIALS
            )
            updates.update(
                status=TaskStatus.NEEDS_INPUT,
                terminal_reason=reason,
                requested_fields=decision.requested_fields,
                requested_details=decision.requested_details,
                terminal_message=decision.terminal_message or "需要补充信息。",
            )
        elif decision.action is DecisionAction.FAIL:
            last = state.get("last_observation")
            if last and last.result_kind is ResultKind.TIMEOUT:
                reason = TerminalReason.TOOL_TIMEOUT
            elif last and last.result_kind is ResultKind.ERROR:
                reason = TerminalReason.TOOL_UNAVAILABLE
            else:
                reason = TerminalReason.CONSTRAINTS_UNSATISFIABLE
            updates.update(
                status=TaskStatus.FAILED,
                terminal_reason=reason,
                terminal_message=decision.terminal_message or "任务执行失败。",
            )
        return updates

    def execute_tool(state: AgentState) -> dict[str, Any]:
        decision = state["pending_decision"]
        if decision is None or decision.action not in TOOL_ACTIONS:
            raise RuntimeError("execute_tool reached without a tool decision.")
        request = state["request"]
        if decision.action is DecisionAction.SEARCH_MATERIALS:
            tool_name = "search_materials"
            arguments = _normalize_search_arguments(decision.tool_args)
        elif decision.action is DecisionAction.ESTIMATE_DURATION:
            tool_name = "estimate_duration"
            arguments = {
                "draft": state["draft"].model_dump(mode="json"),
                "platform": request.platform,
                "target_duration_seconds": request.target_duration_seconds,
            }
        else:
            tool_name = "check_rules"
            arguments = {
                "draft": state["draft"].model_dump(mode="json"),
                "retrieved_material_ids": [
                    item.material_id for item in state.get("retrieved_materials", [])
                ],
                "rules": [
                    item.model_dump(mode="json")
                    for item in state.get("applicable_rules", [])
                ],
                "platform": request.platform,
            }
        try:
            result = tool_registry.invoke(tool_name, arguments)
        except ToolExecutionError as exc:
            result = ToolResult(
                tool_name=tool_name,
                call_id=f"tool-error-{uuid4().hex[:8]}",
                ok=False,
                result_kind=ResultKind.ERROR,
                summary=exc.message,
                error_code=exc.code,
                retryable=exc.retryable,
            )
        except Exception as exc:
            result = ToolResult(
                tool_name=tool_name,
                call_id=f"tool-error-{uuid4().hex[:8]}",
                ok=False,
                result_kind=ResultKind.ERROR,
                summary=f"Unexpected tool failure: {type(exc).__name__}.",
                error_code="unexpected_tool_failure",
                retryable=False,
            )
        return {
            "pending_tool_result": result,
            "pending_tool_args": arguments,
            "tool_call_count": state.get("tool_call_count", 0) + 1,
        }

    def record_observation(state: AgentState) -> dict[str, Any]:
        result = state["pending_tool_result"]
        decision = state["pending_decision"]
        executed_args = state.get("pending_tool_args")
        if result is None or decision is None or executed_args is None:
            raise RuntimeError("record_observation reached without pending values.")
        updates: dict[str, Any] = {
            "last_observation": result,
            "pending_tool_result": None,
            "pending_tool_args": None,
            "pending_decision": None,
        }
        if result.tool_name == "search_materials":
            query = str(executed_args.get("query", ""))
            matches = result.data.get("matches", [])
            match_ids = [
                item.get("material", {}).get("material_id") for item in matches
            ]
            updates["query_history"] = [
                {
                    "query": query,
                    "result_kind": result.result_kind.value,
                    "summary": result.summary,
                    "match_ids": [item for item in match_ids if item],
                }
            ]
            if result.ok and matches:
                merged = {
                    item.material_id: item
                    for item in state.get("retrieved_materials", [])
                }
                for item in matches:
                    material = Material.model_validate(item["material"])
                    merged[material.material_id] = material
                updates["retrieved_materials"] = list(merged.values())
        elif result.tool_name == "estimate_duration":
            if result.ok and "report" in result.data:
                updates["duration_report"] = DurationReport.model_validate(
                    result.data["report"]
                )
        else:
            if result.ok and "report" in result.data:
                updates["rule_report"] = RuleReport.model_validate(
                    result.data["report"]
                )
        event = _trace_event(
            state,
            node="record_observation",
            event_type="tool_result",
            action=decision.action,
            tool_name=result.tool_name,
            proposed_tool_args=decision.tool_args,
            executed_tool_args=executed_args,
            result_kind=result.result_kind,
            result_summary=result.summary,
            draft_revision=state.get("draft").revision if state.get("draft") else None,
        )
        updates["trace_events"] = [event]
        return updates

    def completion_guard(state: AgentState) -> dict[str, Any]:
        draft = state.get("draft")
        duration = state.get("duration_report")
        rules = state.get("rule_report")
        problems: list[str] = []
        if draft is None or not draft.scenes:
            problems.append("script draft is missing")
        if draft is not None:
            fingerprint = canonicalize_draft(draft).fingerprint
            if duration is None:
                problems.append("duration check is missing")
            elif (
                duration.draft_revision != draft.revision
                or duration.draft_fingerprint != fingerprint
            ):
                problems.append("duration check is stale")
            elif not duration.within_limit:
                problems.append("duration check did not pass")
            if rules is None:
                problems.append("rule check is missing")
            elif (
                rules.draft_revision != draft.revision
                or rules.draft_fingerprint != fingerprint
            ):
                problems.append("rule check is stale")
            elif not rules.passed:
                problems.append("rule check did not pass")

        if not problems:
            event = _trace_event(
                state,
                node="completion_guard",
                event_type="guard_accepted",
                action=DecisionAction.FINISH,
                result_kind=ResultKind.SUCCESS,
                result_summary="All completion conditions passed.",
                draft_revision=draft.revision if draft else None,
                status_after=TaskStatus.COMPLETED,
            )
            return {
                "status": TaskStatus.COMPLETED,
                "terminal_reason": TerminalReason.ALL_CHECKS_PASSED,
                "terminal_message": "脚本已通过时长和规则检查。",
                "pending_decision": None,
                "trace_events": [event],
            }

        observation = ToolResult(
            tool_name="completion_guard",
            call_id=f"guard-{uuid4().hex[:8]}",
            ok=True,
            result_kind=ResultKind.REJECTED,
            summary="Finish rejected: " + "; ".join(problems) + ".",
            data={"problems": problems},
        )
        event = _trace_event(
            state,
            node="completion_guard",
            event_type="guard_rejected",
            action=DecisionAction.FINISH,
            tool_name="completion_guard",
            result_kind=ResultKind.REJECTED,
            result_summary=observation.summary,
            draft_revision=draft.revision if draft else None,
        )
        return {
            "status": TaskStatus.RUNNING,
            "last_observation": observation,
            "pending_decision": None,
            "trace_events": [event],
        }

    def terminalize(state: AgentState) -> dict[str, Any]:
        draft = state.get("draft")
        duration = state.get("duration_report")
        rules = state.get("rule_report")
        duration_map = (
            {item.scene_id: item.estimated_seconds for item in duration.scene_durations}
            if duration
            else {}
        )
        scenes = (
            [
                Scene(
                    **scene.model_dump(exclude={"estimated_seconds"}),
                    estimated_seconds=duration_map.get(scene.scene_id),
                )
                for scene in draft.scenes
            ]
            if draft
            else []
        )
        source_ids = sorted(
            {source_id for scene in scenes for source_id in scene.source_ids}
        )
        risks = list(state.get("risks", []))
        if duration is not None:
            risks.append("时长为算法估算值，发布前仍建议真人试读。")
            target = state["request"].target_duration_seconds
            if target and duration.total_seconds < target * 0.7:
                fill_ratio = duration.total_seconds / target
                risks.append(
                    f"脚本预计时长仅达到目标的{fill_ratio:.0%}，可能明显偏短。"
                )
        if rules is not None:
            risks.extend(item.message for item in rules.warnings)
        result = AgentResult(
            status=state.get("status", TaskStatus.FAILED),
            terminal_reason=state.get("terminal_reason"),
            title=draft.title if draft else None,
            scenes=scenes,
            estimated_total_seconds=duration.total_seconds if duration else None,
            target_duration_seconds=state["request"].target_duration_seconds,
            source_ids=source_ids,
            duration_check=duration,
            rule_check=rules,
            risks=risks,
            requested_fields=state.get("requested_fields", []),
            requested_details=state.get("requested_details"),
            message=state.get("terminal_message") or "任务已结束。",
        )
        event = _trace_event(
            state,
            node="terminalize",
            event_type="terminal",
            result_summary=result.message,
            draft_revision=draft.revision if draft else None,
            status_after=result.status,
        )
        return {"result": result, "trace_events": [event]}

    def route_budget(state: AgentState) -> Literal["agent_decide", "terminalize"]:
        return (
            "agent_decide"
            if state.get("status") is TaskStatus.RUNNING
            else "terminalize"
        )

    def route_after_agent(
        state: AgentState,
    ) -> Literal["apply_decision", "budget_before_model", "terminalize"]:
        if state.get("status") is not TaskStatus.RUNNING:
            return "terminalize"
        if state.get("pending_decision") is None:
            return "budget_before_model"
        return "apply_decision"

    def route_after_apply(
        state: AgentState,
    ) -> Literal["budget_before_tool", "completion_guard", "terminalize"]:
        if state.get("status") is not TaskStatus.RUNNING:
            return "terminalize"
        action = state["pending_decision"].action
        if action in TOOL_ACTIONS:
            return "budget_before_tool"
        if action is DecisionAction.FINISH:
            return "completion_guard"
        return "terminalize"

    def route_tool_budget(
        state: AgentState,
    ) -> Literal["execute_tool", "terminalize"]:
        return (
            "execute_tool"
            if state.get("status") is TaskStatus.RUNNING
            else "terminalize"
        )

    def route_completion(
        state: AgentState,
    ) -> Literal["budget_before_model", "terminalize"]:
        return (
            "terminalize"
            if state.get("status") is TaskStatus.COMPLETED
            else "budget_before_model"
        )

    graph = StateGraph(AgentState)
    graph.add_node("prepare_context", prepare_context)
    graph.add_node("budget_before_model", budget_before_model)
    graph.add_node("agent_decide", agent_decide)
    graph.add_node("apply_decision", apply_decision)
    graph.add_node("budget_before_tool", budget_before_tool)
    graph.add_node("execute_tool", execute_tool)
    graph.add_node("record_observation", record_observation)
    graph.add_node("completion_guard", completion_guard)
    graph.add_node("terminalize", terminalize)

    graph.add_edge(START, "prepare_context")
    graph.add_edge("prepare_context", "budget_before_model")
    graph.add_conditional_edges("budget_before_model", route_budget)
    graph.add_conditional_edges("agent_decide", route_after_agent)
    graph.add_conditional_edges("apply_decision", route_after_apply)
    graph.add_conditional_edges("budget_before_tool", route_tool_budget)
    graph.add_edge("execute_tool", "record_observation")
    graph.add_edge("record_observation", "budget_before_model")
    graph.add_conditional_edges("completion_guard", route_completion)
    graph.add_edge("terminalize", END)
    return graph.compile()

