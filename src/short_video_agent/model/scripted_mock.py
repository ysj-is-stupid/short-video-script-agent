"""Observation-driven deterministic adapter for offline verification."""

from __future__ import annotations

from short_video_agent import __version__
from short_video_agent.model.base import DecisionContext
from short_video_agent.schemas import (
    AgentDecision,
    DecisionAction,
    ResultKind,
    Scene,
    ScriptDraft,
)


def _fit_text(base: str, target_characters: int) -> str:
    filler = "内容清楚自然节奏紧凑便于观看理解"
    if len(base) >= target_characters:
        return base
    repeats = (target_characters - len(base)) // len(filler) + 1
    return (base + filler * repeats)[:target_characters]


class ScriptedMockAdapter:
    mode = "mock"

    def __init__(self, scenario: str = "duration_revision") -> None:
        self.scenario = scenario

    @property
    def trace_metadata(self) -> dict[str, str | None]:
        return {
            "provider": "scripted_mock",
            "model_name": self.scenario,
            "sdk_name": None,
            "sdk_version": None,
            "application_name": "short-video-script-agent",
            "application_version": __version__,
            "capture_status": "captured",
        }

    @property
    def last_response_id(self) -> None:
        return None

    def _observation_id(self, context: DecisionContext) -> str | None:
        return context.last_observation.call_id if context.last_observation else None

    def _search_decision(
        self, context: DecisionContext, query: str, reason: str
    ) -> AgentDecision:
        return AgentDecision(
            action=DecisionAction.SEARCH_MATERIALS,
            public_reason=reason,
            based_on_observation_id=self._observation_id(context),
            tool_args={
                "query": query,
                "product_name": context.request.product_name,
                "scope_ids": context.request.material_scope_ids,
                "limit": 5,
            },
        )

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
        target = context.request.target_duration_seconds or 30
        total_characters = max(75, target * 4 - 10) if compact else target * 4 + 30
        first_length = max(28, total_characters // 3)
        second_length = max(20, total_characters // 3)
        third_length = max(20, total_characters - first_length - second_length)

        claim_prefix = fact.statement
        if unsupported_claim:
            claim_prefix += "，效率提升80%"
        scene_one = _fit_text(
            f"面向{context.request.audience or '创作者'}，{claim_prefix}。",
            first_length,
        )
        scene_two = _fit_text(
            f"用{context.request.style or '清晰'}的方式展示创作过程。",
            second_length,
        )
        scene_three = _fit_text(
            f"在{context.request.platform or '短视频平台'}发布前检查文字并完成编辑。",
            third_length,
        )
        return ScriptDraft(
            revision=revision,
            title=f"{context.request.topic or '短视频'}：清晰表达每一步",
            scenes=[
                Scene(
                    scene_id="S01",
                    visual="展示产品中的字幕能力",
                    narration=scene_one,
                    subtitle=claim_prefix,
                    source_ids=[material.material_id],
                    fact_ids=[fact.fact_id],
                ),
                Scene(
                    scene_id="S02",
                    visual="展示创作者编辑短视频",
                    narration=scene_two,
                    subtitle="把内容整理成清晰脚本",
                ),
                Scene(
                    scene_id="S03",
                    visual="展示发布前检查",
                    narration=scene_three,
                    subtitle="检查后再发布",
                ),
            ],
        )

    def decide(self, context: DecisionContext) -> AgentDecision:
        observation_id = self._observation_id(context)
        if context.missing_fields:
            return AgentDecision(
                action=DecisionAction.REQUEST_INPUT,
                public_reason="生成脚本所需的关键信息尚不完整。",
                based_on_observation_id=observation_id,
                requested_fields=context.missing_fields,
                requested_details="请补充所有列出的业务必填字段。",
                terminal_message="请补充缺失字段后重新运行。",
            )

        last = context.last_observation
        if last and last.tool_name in {"estimate_duration", "check_rules"}:
            if last.result_kind in {ResultKind.ERROR, ResultKind.TIMEOUT}:
                return AgentDecision(
                    action=DecisionAction.FAIL,
                    public_reason="业务工具失败或超时，当前无法安全继续。",
                    based_on_observation_id=observation_id,
                    terminal_message="业务工具不可用，任务未完成。",
                )
        if not context.query_history and not context.retrieved_materials:
            return self._search_decision(
                context,
                context.request.topic or "产品素材",
                "需要先检索可追溯的产品事实。",
            )

        if last and last.tool_name == "search_materials":
            if last.result_kind is ResultKind.ERROR:
                error_count = sum(
                    1 for item in context.query_history if item.get("result_kind") == "error"
                )
                if last.retryable and error_count < 2:
                    return self._search_decision(
                        context,
                        context.request.topic or "产品素材",
                        "素材工具发生可重试错误，剩余预算允许再次尝试。",
                    )
                return AgentDecision(
                    action=DecisionAction.FAIL,
                    public_reason="素材工具持续失败，无法获得事实依据。",
                    based_on_observation_id=observation_id,
                    terminal_message="素材检索工具不可用，任务未完成。",
                )
            if last.result_kind is ResultKind.EMPTY:
                if len(context.query_history) < 2:
                    return self._search_decision(
                        context,
                        f"{context.request.product_name or ''} 视频字幕 功能".strip(),
                        "首次检索无结果，改写查询后再次检索。",
                    )
                return AgentDecision(
                    action=DecisionAction.REQUEST_INPUT,
                    public_reason="改写查询后仍无素材，不能编造产品事实。",
                    based_on_observation_id=observation_id,
                    requested_fields=["product_materials"],
                    requested_details="请提供与主题相关且可引用的产品事实素材。",
                    terminal_message="请补充与主题相关的产品素材。",
                )
            if last.result_kind is ResultKind.SUCCESS and context.draft is None:
                unsupported = self.scenario == "unsupported_claim_revision"
                draft = self._make_draft(
                    context,
                    revision=1,
                    compact=self.scenario != "duration_revision",
                    unsupported_claim=unsupported,
                )
                return AgentDecision(
                    action=DecisionAction.ESTIMATE_DURATION,
                    public_reason="已取得素材事实，先生成首稿并检查时长。",
                    based_on_observation_id=observation_id,
                    draft=draft,
                )

        if context.duration_report is not None:
            if not context.duration_report.within_limit:
                revision = (context.draft.revision if context.draft else 1) + 1
                draft = self._make_draft(
                    context,
                    revision=revision,
                    compact=True,
                    unsupported_claim=False,
                )
                return AgentDecision(
                    action=DecisionAction.ESTIMATE_DURATION,
                    public_reason=(
                        f"当前脚本预计{context.duration_report.total_seconds:.1f}秒，"
                        "超过目标，需要压缩后重新估时。"
                    ),
                    based_on_observation_id=observation_id,
                    draft=draft,
                )
            if context.rule_report is None:
                return AgentDecision(
                    action=DecisionAction.CHECK_RULES,
                    public_reason="当前稿时长已通过，需要继续检查素材引用和品牌规则。",
                    based_on_observation_id=observation_id,
                )

        if context.rule_report is not None:
            if context.rule_report.passed:
                return AgentDecision(
                    action=DecisionAction.FINISH,
                    public_reason="当前稿的时长和规则检查均已通过。",
                    based_on_observation_id=observation_id,
                    terminal_message="脚本已完成全部检查。",
                )
            revision = (context.draft.revision if context.draft else 1) + 1
            draft = self._make_draft(
                context,
                revision=revision,
                compact=True,
                unsupported_claim=False,
            )
            return AgentDecision(
                action=DecisionAction.ESTIMATE_DURATION,
                public_reason="规则检查未通过，删除无依据内容并从时长检查重新验证。",
                based_on_observation_id=observation_id,
                draft=draft,
            )

        return AgentDecision(
            action=DecisionAction.FAIL,
            public_reason="当前观察无法形成安全的下一步动作。",
            based_on_observation_id=observation_id,
            terminal_message="任务状态不完整，无法继续。",
        )

