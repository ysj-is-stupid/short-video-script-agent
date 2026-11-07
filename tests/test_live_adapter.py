"""Unit tests for live-model output and transport error boundaries."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from short_video_agent.errors import ModelOutputValidationError
from short_video_agent.model.base import DecisionContext
from short_video_agent.model.openai_adapter import LiveModelAdapter
from short_video_agent.schemas import AgentDecision, DecisionAction, ScriptRequest


class InvalidJsonCompletions:
    def create(self, **_: object) -> SimpleNamespace:
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="not-json"))]
        )


class StubResponses:
    def __init__(self) -> None:
        self.kwargs: dict[str, object] | None = None

    def parse(self, **kwargs: object) -> SimpleNamespace:
        self.kwargs = kwargs
        return SimpleNamespace(
            id="resp_test_123",
            output_parsed=AgentDecision(
                action=DecisionAction.REQUEST_INPUT,
                public_reason="缺少素材，需要用户补充。",
                requested_fields=["product_materials"],
                requested_details="请提供产品事实素材。",
            ),
        )


def context() -> DecisionContext:
    return DecisionContext(
        request=ScriptRequest(
            topic="字幕",
            audience="创作者",
            platform="抖音",
            target_duration_seconds=30,
            style="简洁",
        ),
        remaining_model_steps=2,
        remaining_tool_calls=2,
    )


def test_openai_responses_parse_branch_and_response_id_are_captured() -> None:
    adapter = LiveModelAdapter(
        api_key="test-key",
        model="test-model",
        provider="openai",
    )
    responses = StubResponses()
    adapter._client = SimpleNamespace(responses=responses)

    decision = adapter.decide(context())

    assert decision.action is DecisionAction.REQUEST_INPUT
    assert adapter.last_response_id == "resp_test_123"
    assert adapter.trace_metadata["provider"] == "openai"
    assert adapter.trace_metadata["model_name"] == "test-model"
    assert adapter.trace_metadata["sdk_version"]
    assert responses.kwargs is not None
    assert responses.kwargs["text_format"] is AgentDecision
    assert responses.kwargs["store"] is False


def test_deepseek_invalid_json_is_output_validation_error() -> None:
    adapter = LiveModelAdapter(
        api_key="test-key",
        model="test-model",
        provider="deepseek",
        base_url="https://example.invalid/v1",
    )
    adapter._client = SimpleNamespace(
        chat=SimpleNamespace(completions=InvalidJsonCompletions())
    )
    with pytest.raises(ModelOutputValidationError) as captured:
        adapter.decide(context())

    assert captured.value.code == "invalid_model_output"
    assert "not-json" not in captured.value.message
