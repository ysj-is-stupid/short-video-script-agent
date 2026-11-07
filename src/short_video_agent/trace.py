"""Trace contracts and reviewer-oriented projection."""

from __future__ import annotations

from typing import Any, Mapping, Protocol

from short_video_agent.schemas import TraceEvent


class TraceSink(Protocol):
    def emit(self, event: TraceEvent) -> None:
        """Persist or collect one sanitized trace event."""


def build_review_steps(events: list[TraceEvent]) -> list[dict[str, Any]]:
    """Link each observed tool result to the next decision that actually ran."""

    ordered = sorted(events, key=lambda event: event.sequence)
    steps: list[dict[str, Any]] = []
    for event in ordered:
        if event.event_type not in {"tool_result", "guard_rejected"}:
            continue
        next_decision = next(
            (
                candidate
                for candidate in ordered
                if candidate.sequence > event.sequence
                and candidate.event_type == "decision"
            ),
            None,
        )
        steps.append(
            {
                "step": len(steps) + 1,
                "tool": event.tool_name,
                "proposed_tool_args": event.proposed_tool_args,
                "executed_tool_args": event.executed_tool_args,
                "result_kind": event.result_kind.value if event.result_kind else None,
                "result_summary": event.result_summary,
                "next_action": (
                    next_decision.action.value
                    if next_decision and next_decision.action
                    else None
                ),
                "decision_basis": (
                    next_decision.public_reason if next_decision else None
                ),
                "draft_revision": event.draft_revision,
            }
        )
    return steps


def build_trace_payload(
    events: list[TraceEvent],
    *,
    model_mode: str,
    scenario: str | None = None,
    model_metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = dict(model_metadata or {})
    metadata["response_ids"] = list(
        dict.fromkeys(
            event.model_response_id
            for event in events
            if event.model_response_id is not None
        )
    )
    return {
        "trace_schema_version": "2.0",
        "model_mode": model_mode,
        "model_metadata": metadata,
        "scenario": scenario,
        "mock_boundary": (
            "Mock traces verify flow and state transitions, not real-model decision quality."
            if model_mode == "mock"
            else None
        ),
        "review_steps": build_review_steps(events),
        "raw_events": [event.model_dump(mode="json") for event in events],
    }

