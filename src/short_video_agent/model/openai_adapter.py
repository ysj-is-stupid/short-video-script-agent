"""Live OpenAI Responses API adapter with Pydantic structured output."""

from __future__ import annotations

import json
from importlib.metadata import version

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI
from pydantic import ValidationError

from short_video_agent.errors import (
    ConfigurationError,
    ModelAdapterError,
    ModelOutputValidationError,
)
from short_video_agent import __version__
from short_video_agent.model.base import DecisionContext
from short_video_agent.prompts import AGENT_INSTRUCTIONS
from short_video_agent.schemas import AgentDecision


class LiveModelAdapter:
    mode = "live"

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str | None,
        provider: str = "openai",
        base_url: str | None = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        if not api_key:
            raise ConfigurationError(
                code="missing_model_api_key",
                message="A model API key is required when MODEL_MODE=live.",
            )
        if not model:
            raise ConfigurationError(
                code="missing_model_name",
                message="A model name is required when MODEL_MODE=live.",
            )
        if provider not in {"openai", "deepseek"}:
            raise ConfigurationError(
                code="unsupported_model_provider",
                message=f"Unsupported model provider: {provider}",
            )
        client_args = {"api_key": api_key, "timeout": timeout_seconds}
        if base_url:
            client_args["base_url"] = base_url
        self._client = OpenAI(**client_args)
        self._model = model
        self._provider = provider
        self._last_response_id: str | None = None

    @property
    def trace_metadata(self) -> dict[str, str | None]:
        return {
            "provider": self._provider,
            "model_name": self._model,
            "sdk_name": "openai",
            "sdk_version": version("openai"),
            "application_name": "short-video-script-agent",
            "application_version": __version__,
            "capture_status": "captured",
        }

    @property
    def last_response_id(self) -> str | None:
        return self._last_response_id

    def _decision_input(self, context: DecisionContext) -> str:
        payload = {
            "state": context.model_dump(mode="json"),
            "output_json_schema": AgentDecision.model_json_schema(),
        }
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    def decide(self, context: DecisionContext) -> AgentDecision:
        self._last_response_id = None
        try:
            if self._provider == "openai":
                response = self._client.responses.parse(
                    model=self._model,
                    instructions=AGENT_INSTRUCTIONS,
                    input=self._decision_input(context),
                    text_format=AgentDecision,
                    store=False,
                    max_output_tokens=2000,
                )
                self._last_response_id = str(getattr(response, "id", "") or "") or None
                decision = response.output_parsed
            else:
                response = self._client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": AGENT_INSTRUCTIONS},
                        {"role": "user", "content": self._decision_input(context)},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0,
                    max_tokens=2000,
                )
                content = response.choices[0].message.content
                self._last_response_id = str(getattr(response, "id", "") or "") or None
                decision = (
                    AgentDecision.model_validate_json(content) if content else None
                )
        except ValidationError as exc:
            raise ModelOutputValidationError(
                code="invalid_model_output",
                message=(
                    "Model returned JSON that does not satisfy AgentDecision "
                    f"({exc.error_count()} validation error(s))."
                ),
                retryable=True,
            ) from exc
        except (APIConnectionError, APITimeoutError) as exc:
            raise ModelAdapterError(
                code="model_transport_error",
                message="Live model request failed due to connection or timeout.",
                retryable=True,
            ) from exc
        except APIStatusError as exc:
            retryable = exc.status_code in {408, 409, 429} or exc.status_code >= 500
            raise ModelAdapterError(
                code="model_http_error",
                message=f"Live model request returned HTTP {exc.status_code}.",
                retryable=retryable,
            ) from exc
        except Exception as exc:
            raise ModelAdapterError(
                code="unexpected_model_adapter_error",
                message=(
                    "Live model adapter failed unexpectedly: "
                    f"{type(exc).__name__}."
                ),
                retryable=False,
            ) from exc

        if decision is None:
            raise ModelOutputValidationError(
                code="live_model_decision_missing",
                message="Live model response did not contain an AgentDecision JSON object.",
                retryable=True,
            )
        return decision


OpenAIModelAdapter = LiveModelAdapter

