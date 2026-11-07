"""Pydantic contracts shared across the Agent, tools and CLI."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    """Base class that rejects accidental or misspelled fields."""

    model_config = ConfigDict(extra="forbid")


class TaskStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    NEEDS_INPUT = "needs_input"
    INCOMPLETE = "incomplete"
    FAILED = "failed"


class TerminalReason(str, Enum):
    ALL_CHECKS_PASSED = "all_checks_passed"
    MISSING_REQUIRED_FIELDS = "missing_required_fields"
    NO_SUPPORTING_MATERIALS = "no_supporting_materials"
    AMBIGUOUS_USER_CONSTRAINT = "ambiguous_user_constraint"
    MODEL_STEP_LIMIT_REACHED = "model_step_limit_reached"
    TOOL_CALL_LIMIT_REACHED = "tool_call_limit_reached"
    MODEL_OUTPUT_INVALID = "model_output_invalid"
    TOOL_UNAVAILABLE = "tool_unavailable"
    TOOL_TIMEOUT = "tool_timeout"
    CONSTRAINTS_UNSATISFIABLE = "constraints_unsatisfiable"
    INTERNAL_ERROR = "internal_error"


class DecisionAction(str, Enum):
    SEARCH_MATERIALS = "search_materials"
    ESTIMATE_DURATION = "estimate_duration"
    CHECK_RULES = "check_rules"
    FINISH = "finish"
    REQUEST_INPUT = "request_input"
    FAIL = "fail"


class RequestedField(str, Enum):
    TOPIC = "topic"
    AUDIENCE = "audience"
    PLATFORM = "platform"
    TARGET_DURATION_SECONDS = "target_duration_seconds"
    STYLE = "style"
    PRODUCT_NAME = "product_name"
    PRODUCT_MATERIALS = "product_materials"
    BRAND_RULES = "brand_rules"
    VALIDATED_SCRIPT = "validated_script"


class ResultKind(str, Enum):
    SUCCESS = "success"
    EMPTY = "empty"
    REJECTED = "rejected"
    ERROR = "error"
    TIMEOUT = "timeout"


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"


class ScriptRequest(StrictModel):
    """Transport request.

    Business-required fields are nullable so missing information can become an
    observation and be handled by the Agent instead of failing JSON parsing.
    """

    topic: str | None = None
    audience: str | None = None
    platform: str | None = None
    target_duration_seconds: int | None = Field(
        default=None, ge=1, le=600, strict=True
    )
    style: str | None = None
    product_name: str | None = None
    material_scope_ids: list[str] = Field(default_factory=list)
    brand_rule_scope_ids: list[str] = Field(default_factory=list)

    @field_validator(
        "topic", "audience", "platform", "style", "product_name", mode="before"
    )
    @classmethod
    def normalize_optional_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip() or None
        return value

    @property
    def missing_required_fields(self) -> list[str]:
        required_fields = (
            "topic",
            "audience",
            "platform",
            "target_duration_seconds",
            "style",
        )
        return [name for name in required_fields if getattr(self, name) is None]


class MaterialFact(StrictModel):
    fact_id: str
    statement: str
    keywords: list[str] = Field(default_factory=list)
    allowed_numbers: list[str] = Field(default_factory=list)


class Material(StrictModel):
    material_id: str
    product_name: str
    aliases: list[str] = Field(default_factory=list)
    title: str
    facts: list[MaterialFact] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class BrandRule(StrictModel):
    rule_id: str
    description: str
    severity: Severity = Severity.ERROR
    forbidden_terms: list[str] = Field(default_factory=list)
    required_terms: list[str] = Field(default_factory=list)
    applies_to_platforms: list[str] = Field(default_factory=list)


class Scene(StrictModel):
    scene_id: str
    visual: str
    narration: str | None = None
    subtitle: str | None = None
    source_ids: list[str] = Field(default_factory=list)
    fact_ids: list[str] = Field(default_factory=list)
    estimated_seconds: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def require_spoken_or_displayed_text(self) -> Self:
        if not (self.narration or self.subtitle):
            raise ValueError("A scene requires narration or subtitle text.")
        return self


class ScriptDraft(StrictModel):
    revision: int = Field(ge=1)
    title: str
    scenes: list[Scene] = Field(min_length=1)
    fingerprint: str | None = None


class SceneDuration(StrictModel):
    scene_id: str
    estimated_seconds: float = Field(ge=0)


class DurationReport(StrictModel):
    draft_revision: int = Field(ge=1)
    draft_fingerprint: str
    scene_durations: list[SceneDuration]
    total_seconds: float = Field(ge=0)
    target_seconds: int = Field(ge=1)
    over_by_seconds: float = Field(ge=0)
    within_limit: bool
    estimation_method: str


class RuleViolation(StrictModel):
    code: str
    severity: Severity
    scene_id: str | None = None
    message: str
    related_source_ids: list[str] = Field(default_factory=list)
    related_fact_ids: list[str] = Field(default_factory=list)


class RuleReport(StrictModel):
    draft_revision: int = Field(ge=1)
    draft_fingerprint: str
    passed: bool
    violations: list[RuleViolation] = Field(default_factory=list)
    warnings: list[RuleViolation] = Field(default_factory=list)
    checked_source_ids: list[str] = Field(default_factory=list)


class ToolResult(StrictModel):
    tool_name: str
    call_id: str
    ok: bool
    result_kind: ResultKind
    summary: str
    data: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None
    retryable: bool = False


class AgentDecision(StrictModel):
    action: DecisionAction
    public_reason: str
    based_on_observation_id: str | None = None
    tool_args: dict[str, Any] = Field(default_factory=dict)
    draft: ScriptDraft | None = None
    requested_fields: list[RequestedField] = Field(default_factory=list)
    requested_details: str | None = None
    terminal_message: str | None = None


class TraceEvent(StrictModel):
    event_id: str
    sequence: int = Field(ge=1)
    timestamp: datetime
    node: str
    event_type: str
    model_step: int = Field(ge=0)
    tool_call_count: int = Field(ge=0)
    action: DecisionAction | None = None
    public_reason: str | None = None
    tool_name: str | None = None
    proposed_tool_args: dict[str, Any] = Field(default_factory=dict)
    executed_tool_args: dict[str, Any] = Field(default_factory=dict)
    model_response_id: str | None = None
    result_kind: ResultKind | None = None
    result_summary: str | None = None
    draft_revision: int | None = None
    status_after: TaskStatus
    based_on_observation_id: str | None = None


class AgentResult(StrictModel):
    status: TaskStatus
    terminal_reason: TerminalReason | None = None
    title: str | None = None
    scenes: list[Scene] = Field(default_factory=list)
    estimated_total_seconds: float | None = Field(default=None, ge=0)
    target_duration_seconds: int | None = Field(default=None, ge=1)
    source_ids: list[str] = Field(default_factory=list)
    duration_check: DurationReport | None = None
    rule_check: RuleReport | None = None
    risks: list[str] = Field(default_factory=list)
    requested_fields: list[RequestedField] = Field(default_factory=list)
    requested_details: str | None = None
    message: str
    trace_file: str | None = None

