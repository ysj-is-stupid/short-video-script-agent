"""Environment-backed application configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

from dotenv import dotenv_values, find_dotenv

from short_video_agent.errors import ConfigurationError


def _read_positive_int(
    values: Mapping[str, str], name: str, default: int
) -> int:
    raw_value = values.get(name, str(default))
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ConfigurationError(
            code="invalid_integer_config",
            message=f"{name} must be an integer.",
        ) from exc
    if value <= 0:
        raise ConfigurationError(
            code="non_positive_config",
            message=f"{name} must be greater than zero.",
        )
    return value


def _read_positive_float(
    values: Mapping[str, str], name: str, default: float
) -> float:
    raw_value = values.get(name, str(default))
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise ConfigurationError(
            code="invalid_float_config",
            message=f"{name} must be a number.",
        ) from exc
    if value <= 0:
        raise ConfigurationError(
            code="non_positive_config",
            message=f"{name} must be greater than zero.",
        )
    return value


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Configuration shared by CLI, graph, model adapter and budget guards."""

    model_mode: str = "mock"
    model_provider: str = "openai"
    model_api_key: str | None = None
    model_name: str | None = None
    model_base_url: str | None = None
    model_timeout_seconds: float = 60.0
    max_model_steps: int = 10
    max_tool_calls: int = 8
    max_invalid_decisions: int = 2

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "AppConfig":
        if environ is None:
            dotenv_path = find_dotenv(usecwd=True)
            file_values = {
                key: value
                for key, value in (
                    dotenv_values(dotenv_path).items() if dotenv_path else []
                )
                if value is not None
            }
            values: Mapping[str, str] = {**file_values, **os.environ}
        else:
            values = environ
        deepseek_key = values.get("DEEPSEEK_API_KEY", "").strip() or None
        deepseek_model = values.get("DEEPSEEK_MODEL", "").strip() or None
        deepseek_base_url = values.get("DEEPSEEK_BASE_URL", "").strip() or None
        openai_key = values.get("OPENAI_API_KEY", "").strip() or None
        openai_model = values.get("OPENAI_MODEL", "").strip() or None
        openai_base_url = values.get("OPENAI_BASE_URL", "").strip() or None

        configured_provider = values.get("MODEL_PROVIDER", "").strip().lower()
        if configured_provider:
            model_provider = configured_provider
        elif deepseek_key or deepseek_model or deepseek_base_url:
            model_provider = "deepseek"
        else:
            model_provider = "openai"
        if model_provider not in {"openai", "deepseek"}:
            raise ConfigurationError(
                code="invalid_model_provider",
                message="MODEL_PROVIDER must be either 'openai' or 'deepseek'.",
            )

        if model_provider == "deepseek":
            api_key = deepseek_key
            model_name = deepseek_model
            base_url = deepseek_base_url
        else:
            api_key = openai_key
            model_name = openai_model
            base_url = openai_base_url

        raw_mode = values.get("MODEL_MODE", "").strip().lower()
        # Credentials select the provider configuration, but never authorize a
        # network request by themselves. Live execution must be explicit.
        model_mode = raw_mode or "mock"
        if model_mode not in {"mock", "live"}:
            raise ConfigurationError(
                code="invalid_model_mode",
                message="MODEL_MODE must be either 'mock' or 'live'.",
            )

        return cls(
            model_mode=model_mode,
            model_provider=model_provider,
            model_api_key=api_key,
            model_name=model_name,
            model_base_url=base_url,
            model_timeout_seconds=_read_positive_float(
                values, "MODEL_TIMEOUT_SECONDS", 60.0
            ),
            max_model_steps=_read_positive_int(values, "MAX_MODEL_STEPS", 10),
            max_tool_calls=_read_positive_int(values, "MAX_TOOL_CALLS", 8),
            max_invalid_decisions=_read_positive_int(
                values, "MAX_INVALID_DECISIONS", 2
            ),
        )

