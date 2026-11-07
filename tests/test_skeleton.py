"""Minimal checks for the engineering skeleton and shared contracts."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from short_video_agent import __version__
from short_video_agent.config import AppConfig
from short_video_agent.schemas import ScriptRequest
from short_video_agent.tools import ToolRegistry


def test_package_version_is_exposed() -> None:
    assert __version__ == "0.1.0"


def test_missing_business_fields_are_preserved_for_agent_path() -> None:
    request = ScriptRequest(topic="字幕功能")

    assert request.topic == "字幕功能"
    assert request.missing_required_fields == [
        "audience",
        "platform",
        "target_duration_seconds",
        "style",
    ]


def test_blank_business_text_becomes_missing() -> None:
    request = ScriptRequest(
        topic="   ",
        audience="创作者",
        platform="抖音",
        target_duration_seconds=30,
        style="简洁",
    )

    assert request.topic is None
    assert request.missing_required_fields == ["topic"]


def test_invalid_duration_is_rejected_before_graph() -> None:
    with pytest.raises(ValidationError):
        ScriptRequest(target_duration_seconds=-1)


def test_config_defaults_are_offline_and_bounded() -> None:
    config = AppConfig.from_env({})

    assert config.model_mode == "mock"
    assert config.max_model_steps == 10
    assert config.max_tool_calls == 8
    assert config.max_invalid_decisions == 2


def test_deepseek_credentials_do_not_implicitly_enable_live_mode() -> None:
    config = AppConfig.from_env(
        {
            "DEEPSEEK_API_KEY": "test-key",
            "DEEPSEEK_BASE_URL": "https://example.invalid/v1",
            "DEEPSEEK_MODEL": "test-model",
        }
    )

    assert config.model_mode == "mock"
    assert config.model_provider == "deepseek"
    assert config.model_api_key == "test-key"
    assert config.model_base_url == "https://example.invalid/v1"
    assert config.model_name == "test-model"


def test_live_mode_requires_an_explicit_mode_setting() -> None:
    config = AppConfig.from_env(
        {
            "MODEL_MODE": "live",
            "DEEPSEEK_API_KEY": "test-key",
            "DEEPSEEK_BASE_URL": "https://example.invalid/v1",
            "DEEPSEEK_MODEL": "test-model",
        }
    )

    assert config.model_mode == "live"
    assert config.model_provider == "deepseek"


def test_tool_registry_starts_empty() -> None:
    assert ToolRegistry().names == ()

