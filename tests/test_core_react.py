"""Core ReAct graph tests using observable, deterministic model adapters."""

from __future__ import annotations

from short_video_agent.config import AppConfig
from short_video_agent.errors import ModelAdapterError, ModelOutputValidationError
from short_video_agent.model.base import DecisionContext
from short_video_agent.model.scripted_mock import ScriptedMockAdapter
from short_video_agent.runtime import run_agent
from short_video_agent.schemas import (
    AgentDecision,
    BrandRule,
    DecisionAction,
    Material,
    MaterialFact,
    Scene,
    ScriptDraft,
    ScriptRequest,
    Severity,
    TaskStatus,
    TerminalReason,
)


def complete_request() -> ScriptRequest:
    return ScriptRequest(
        topic="字幕功能",
        audience="短视频创作者",
        platform="抖音",
        target_duration_seconds=30,
        style="简洁",
        product_name="示例产品",
    )


def product_materials() -> list[Material]:
    return [
        Material(
            material_id="P01",
            product_name="示例产品",
            title="字幕功能说明",
            facts=[
                MaterialFact(
                    fact_id="P01-F01",
                    statement="支持字幕",
                    keywords=["字幕"],
                )
            ],
            tags=["字幕", "视频"],
        )
    ]


def brand_rules() -> list[BrandRule]:
    return [
        BrandRule(
            rule_id="B01",
            description="不得使用绝对化宣传",
            severity=Severity.ERROR,
            forbidden_terms=["行业第一"],
        )
    ]


def decision_actions(outcome: object) -> list[str]:
    return [
        event.action.value
        for event in outcome.trace_events
        if event.event_type == "decision" and event.action is not None
    ]


def test_duration_observation_causes_revision_and_second_estimate() -> None:
    outcome = run_agent(
        request=complete_request(),
        materials=product_materials(),
        rules=brand_rules(),
        model_adapter=ScriptedMockAdapter("duration_revision"),
        config=AppConfig(),
    )

    assert outcome.result.status is TaskStatus.COMPLETED
    assert outcome.result.terminal_reason is TerminalReason.ALL_CHECKS_PASSED
    assert outcome.result.estimated_total_seconds is not None
    assert outcome.result.estimated_total_seconds <= 30
    assert outcome.result.source_ids == ["P01"]
    assert decision_actions(outcome) == [
        "search_materials",
        "estimate_duration",
        "estimate_duration",
        "check_rules",
        "finish",
    ]
    duration_summaries = [
        event.result_summary
        for event in outcome.trace_events
        if event.tool_name == "estimate_duration"
        and event.event_type == "tool_result"
    ]
    assert len(duration_summaries) == 2
    assert "Estimated 38.1s" in duration_summaries[0]
    assert "within_limit=false" in duration_summaries[0]
    assert "Estimated 28.0s" in duration_summaries[1]
    assert "within_limit=true" in duration_summaries[1]
    decision_events = [
        event for event in outcome.trace_events if event.event_type == "decision"
    ]
    assert [event.model_step for event in decision_events] == [1, 2, 3, 4, 5]
    first_tool_result = next(
        event
        for event in outcome.trace_events
        if event.event_type == "tool_result"
        and event.tool_name == "search_materials"
    )
    assert first_tool_result.proposed_tool_args["limit"] == 5
    assert first_tool_result.executed_tool_args["limit"] == 5


class UnknownSearchParameterAdapter(ScriptedMockAdapter):
    def decide(self, context: DecisionContext) -> AgentDecision:
        decision = super().decide(context)
        if decision.action is DecisionAction.SEARCH_MATERIALS:
            return decision.model_copy(
                update={
                    "tool_args": {
                        "query": "字幕功能",
                        "scope_ids": ["P01"],
                        "top_k": 99,
                    }
                }
            )
        return decision


def test_trace_separates_model_proposal_from_normalized_execution_args() -> None:
    outcome = run_agent(
        request=complete_request(),
        materials=product_materials(),
        rules=brand_rules(),
        model_adapter=UnknownSearchParameterAdapter("duration_revision"),
        config=AppConfig(),
    )

    search_result = next(
        event
        for event in outcome.trace_events
        if event.event_type == "tool_result"
        and event.tool_name == "search_materials"
    )
    assert search_result.proposed_tool_args["top_k"] == 99
    assert "top_k" not in search_result.executed_tool_args
    assert search_result.executed_tool_args == {
        "query": "字幕功能",
        "product_name": "",
        "scope_ids": ["P01"],
        "limit": 5,
    }


def test_empty_search_observation_causes_query_rewrite_then_needs_input() -> None:
    outcome = run_agent(
        request=complete_request(),
        materials=[],
        rules=brand_rules(),
        model_adapter=ScriptedMockAdapter("query_rewrite"),
        config=AppConfig(),
    )

    assert outcome.result.status is TaskStatus.NEEDS_INPUT
    assert outcome.result.terminal_reason is TerminalReason.NO_SUPPORTING_MATERIALS
    assert outcome.result.requested_fields == ["product_materials"]
    assert decision_actions(outcome) == [
        "search_materials",
        "search_materials",
        "request_input",
    ]
    queries = [item["query"] for item in outcome.final_state["query_history"]]
    assert len(queries) == 2
    assert queries[0] != queries[1]


class PrematureFinishAdapter:
    mode = "mock"

    def decide(self, context: DecisionContext) -> AgentDecision:
        if context.last_observation and context.last_observation.tool_name == "completion_guard":
            return AgentDecision(
                action=DecisionAction.REQUEST_INPUT,
                public_reason="完成守卫指出检查缺失，需要外部补充。",
                requested_fields=["validated_script"],
            )
        return AgentDecision(
            action=DecisionAction.FINISH,
            public_reason="故意提前完成，用于验证守卫。",
        )


def test_completion_guard_rejects_unchecked_finish() -> None:
    outcome = run_agent(
        request=complete_request(),
        materials=product_materials(),
        rules=brand_rules(),
        model_adapter=PrematureFinishAdapter(),
        config=AppConfig(),
    )

    assert outcome.result.status is TaskStatus.NEEDS_INPUT
    assert any(event.event_type == "guard_rejected" for event in outcome.trace_events)


class EndlessSearchAdapter:
    mode = "mock"

    def decide(self, context: DecisionContext) -> AgentDecision:
        return AgentDecision(
            action=DecisionAction.SEARCH_MATERIALS,
            public_reason="持续检索，用于验证工具预算。",
            tool_args={"query": "不存在的素材"},
        )


def test_tool_budget_returns_explicit_incomplete_status() -> None:
    outcome = run_agent(
        request=complete_request(),
        materials=[],
        rules=[],
        model_adapter=EndlessSearchAdapter(),
        config=AppConfig(max_tool_calls=1),
    )

    assert outcome.result.status is TaskStatus.INCOMPLETE
    assert outcome.result.terminal_reason is TerminalReason.TOOL_CALL_LIMIT_REACHED
    assert outcome.final_state["tool_call_count"] == 1


def test_model_budget_returns_explicit_incomplete_status() -> None:
    outcome = run_agent(
        request=complete_request(),
        materials=product_materials(),
        rules=[],
        model_adapter=PrematureFinishAdapter(),
        config=AppConfig(max_model_steps=1),
    )

    assert outcome.result.status is TaskStatus.INCOMPLETE
    assert outcome.result.terminal_reason is TerminalReason.MODEL_STEP_LIMIT_REACHED
    assert outcome.final_state["model_step_count"] == 1


class TransientFailureThenRecoverAdapter:
    mode = "mock"

    def __init__(self) -> None:
        self.calls = 0
        self.delegate = ScriptedMockAdapter("duration_revision")

    def decide(self, context: DecisionContext) -> AgentDecision:
        self.calls += 1
        if self.calls == 1:
            raise ModelAdapterError(
                code="temporary_upstream_error",
                message="temporary upstream failure",
                retryable=True,
            )
        return self.delegate.decide(context)


def test_retryable_model_transport_error_does_not_count_as_invalid_action() -> None:
    outcome = run_agent(
        request=complete_request(),
        materials=product_materials(),
        rules=brand_rules(),
        model_adapter=TransientFailureThenRecoverAdapter(),
        config=AppConfig(),
    )

    assert outcome.result.status is TaskStatus.COMPLETED
    assert outcome.final_state["invalid_decision_count"] == 0
    assert any(
        event.event_type == "model_request_error" for event in outcome.trace_events
    )


class AlwaysInvalidOutputAdapter:
    mode = "mock"

    def decide(self, context: DecisionContext) -> AgentDecision:
        raise ModelOutputValidationError(
            code="invalid_model_output",
            message="model output failed schema validation",
            retryable=True,
        )


def test_invalid_model_output_consumes_invalid_action_budget() -> None:
    outcome = run_agent(
        request=complete_request(),
        materials=product_materials(),
        rules=[],
        model_adapter=AlwaysInvalidOutputAdapter(),
        config=AppConfig(max_invalid_decisions=2),
    )

    assert outcome.result.status is TaskStatus.FAILED
    assert outcome.result.terminal_reason is TerminalReason.MODEL_OUTPUT_INVALID
    assert outcome.final_state["invalid_decision_count"] == 2
    decision_errors = [
        event for event in outcome.trace_events if event.event_type == "decision_error"
    ]
    assert len(decision_errors) == 2
    assert not any(
        event.event_type == "model_request_error" for event in outcome.trace_events
    )


def test_duration_timeout_becomes_explicit_tool_timeout_failure() -> None:
    outcome = run_agent(
        request=complete_request(),
        materials=product_materials(),
        rules=brand_rules(),
        model_adapter=ScriptedMockAdapter("duration_revision"),
        config=AppConfig(),
        duration_fault="timeout",
    )

    assert outcome.result.status is TaskStatus.FAILED
    assert outcome.result.terminal_reason is TerminalReason.TOOL_TIMEOUT
    assert any(
        event.tool_name == "estimate_duration"
        and event.result_kind.value == "timeout"
        for event in outcome.trace_events
    )


def test_rule_tool_error_becomes_explicit_tool_unavailable_failure() -> None:
    outcome = run_agent(
        request=complete_request(),
        materials=product_materials(),
        rules=brand_rules(),
        model_adapter=ScriptedMockAdapter("duration_revision"),
        config=AppConfig(),
        rule_fault="error",
    )

    assert outcome.result.status is TaskStatus.FAILED
    assert outcome.result.terminal_reason is TerminalReason.TOOL_UNAVAILABLE
    assert any(
        event.tool_name == "check_rules" and event.result_kind.value == "error"
        for event in outcome.trace_events
    )


def test_unexpected_duration_exception_is_sanitized_as_tool_failure() -> None:
    outcome = run_agent(
        request=complete_request(),
        materials=product_materials(),
        rules=brand_rules(),
        model_adapter=ScriptedMockAdapter("duration_revision"),
        config=AppConfig(),
        duration_fault="exception",
    )

    assert outcome.result.terminal_reason is TerminalReason.TOOL_UNAVAILABLE
    failure = next(
        event
        for event in outcome.trace_events
        if event.tool_name == "estimate_duration"
        and event.event_type == "tool_result"
    )
    assert failure.result_kind.value == "error"
    assert "Unexpected tool failure" in failure.result_summary


class SameRevisionAdapter(ScriptedMockAdapter):
    def decide(self, context: DecisionContext) -> AgentDecision:
        decision = super().decide(context)
        if decision.draft is not None and context.draft is not None:
            decision = decision.model_copy(
                update={
                    "draft": decision.draft.model_copy(
                        update={"revision": context.draft.revision}
                    )
                }
            )
        return decision


def test_every_resubmitted_draft_requires_a_strictly_new_revision() -> None:
    outcome = run_agent(
        request=complete_request(),
        materials=product_materials(),
        rules=brand_rules(),
        model_adapter=SameRevisionAdapter("duration_revision"),
        config=AppConfig(max_invalid_decisions=2),
    )

    assert outcome.result.status is TaskStatus.FAILED
    assert outcome.result.terminal_reason is TerminalReason.MODEL_OUTPUT_INVALID
    assert outcome.final_state["invalid_decision_count"] == 2


class UnderfilledDraftAdapter(ScriptedMockAdapter):
    def _make_draft(
        self,
        context: DecisionContext,
        *,
        revision: int,
        compact: bool,
        unsupported_claim: bool = False,
    ) -> ScriptDraft:
        material = context.retrieved_materials[0]
        fact = material.facts[0]
        return ScriptDraft(
            revision=revision,
            title="短稿",
            scenes=[
                Scene(
                    scene_id="S01",
                    visual="展示字幕功能",
                    narration="支持字幕。",
                    source_ids=[material.material_id],
                    fact_ids=[fact.fact_id],
                )
            ],
        )


def test_completed_but_underfilled_script_has_an_explicit_risk() -> None:
    outcome = run_agent(
        request=complete_request(),
        materials=product_materials(),
        rules=brand_rules(),
        model_adapter=UnderfilledDraftAdapter("compact"),
        config=AppConfig(),
    )

    assert outcome.result.status is TaskStatus.COMPLETED
    assert any("明显偏短" in risk for risk in outcome.result.risks)

