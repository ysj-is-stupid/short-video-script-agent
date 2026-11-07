"""Assertions over committed inputs, outputs and traces."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def case(name: str) -> tuple[dict, dict, dict]:
    directory = EXAMPLES / name
    return (
        load_json(directory / "input.json"),
        load_json(directory / "output.json"),
        load_json(directory / "trace.json"),
    )


def actions(trace: dict) -> list[str]:
    return [
        event["action"]
        for event in trace["raw_events"]
        if event["event_type"] == "decision"
    ]


def test_committed_normal_example_is_grounded_and_revised() -> None:
    _, output, trace = case("01-normal-duration-revision")

    assert output["status"] == "completed"
    assert output["estimated_total_seconds"] == 28.0
    assert output["source_ids"] == ["P01"]
    assert output["duration_check"]["draft_revision"] == 2
    assert output["rule_check"]["draft_revision"] == 2
    assert all(
        fact_id == "P01-F01"
        for scene in output["scenes"]
        for fact_id in scene["fact_ids"]
    )
    assert actions(trace) == [
        "search_materials",
        "estimate_duration",
        "estimate_duration",
        "check_rules",
        "finish",
    ]
    duration_steps = [
        step for step in trace["review_steps"] if step["tool"] == "estimate_duration"
    ]
    assert "38.1s" in duration_steps[0]["result_summary"]
    assert duration_steps[0]["next_action"] == "estimate_duration"
    assert "28.0s" in duration_steps[1]["result_summary"]


def test_committed_missing_information_example_calls_no_business_tool() -> None:
    _, output, trace = case("02-missing-information")

    assert output["status"] == "needs_input"
    assert output["terminal_reason"] == "missing_required_fields"
    assert output["requested_fields"] == ["audience"]
    assert trace["review_steps"] == []
    assert actions(trace) == ["request_input"]


def test_committed_no_material_example_rewrites_query() -> None:
    _, output, trace = case("03-no-materials")

    assert output["status"] == "needs_input"
    search_steps = [
        step for step in trace["review_steps"] if step["tool"] == "search_materials"
    ]
    assert len(search_steps) == 2
    assert search_steps[0]["executed_tool_args"]["query"] != search_steps[1]["executed_tool_args"]["query"]
    assert search_steps[0]["next_action"] == "search_materials"
    assert search_steps[1]["next_action"] == "request_input"


def test_committed_tool_failure_example_keeps_errors_distinct() -> None:
    _, output, trace = case("04-tool-failure")

    assert output["status"] == "failed"
    assert output["terminal_reason"] == "tool_unavailable"
    assert [step["result_kind"] for step in trace["review_steps"]] == [
        "error",
        "error",
    ]
    assert actions(trace) == ["search_materials", "search_materials", "fail"]


def test_committed_unsupported_claim_is_removed_after_rejection() -> None:
    _, output, trace = case("05-unsupported-claim-revision")

    assert output["status"] == "completed"
    assert "80%" not in json.dumps(output, ensure_ascii=False)
    rejected = [
        step
        for step in trace["review_steps"]
        if step["tool"] == "check_rules" and step["result_kind"] == "rejected"
    ]
    assert len(rejected) == 1
    assert "unsupported_numeric_claim" in rejected[0]["result_summary"]
    assert rejected[0]["next_action"] == "estimate_duration"


def test_committed_live_normal_path_completed_with_grounded_source() -> None:
    _, output, trace = case("live-01-normal")

    assert trace["model_mode"] == "live"
    assert trace["mock_boundary"] is None
    assert trace["trace_schema_version"] == "2.0"
    assert trace["model_metadata"]["provider"] == "deepseek"
    assert trace["model_metadata"]["capture_status"] == "historical_run_metadata_not_captured"
    assert output["status"] == "completed"
    assert output["source_ids"] == ["P01"]
    assert output["duration_check"]["within_limit"] is True
    assert output["rule_check"]["passed"] is True
    assert actions(trace) == [
        "search_materials",
        "estimate_duration",
        "check_rules",
        "finish",
    ]
    final_text = json.dumps(output["scenes"], ensure_ascii=False)
    for unsupported_term in ("手打", "省心", "好用", "自动", "一键", "提升"):
        assert unsupported_term not in final_text


def test_committed_live_empty_search_path_rewrites_then_requests_input() -> None:
    _, output, trace = case("live-02-no-materials")

    assert trace["model_mode"] == "live"
    assert output["status"] == "needs_input"
    assert output["title"] is None
    assert output["requested_fields"] == ["product_materials"]
    assert output["requested_details"]
    search_steps = [
        step for step in trace["review_steps"] if step["tool"] == "search_materials"
    ]
    assert len(search_steps) == 2
    assert search_steps[0]["executed_tool_args"]["query"] != search_steps[1]["executed_tool_args"]["query"]
    assert search_steps[0]["next_action"] == "search_materials"
    assert search_steps[1]["next_action"] == "request_input"


def test_committed_duration_timeout_example_is_explicit() -> None:
    _, output, trace = case("06-duration-timeout")

    assert output["status"] == "failed"
    assert output["terminal_reason"] == "tool_timeout"
    assert any(
        step["tool"] == "estimate_duration" and step["result_kind"] == "timeout"
        for step in trace["review_steps"]
    )


def test_committed_rule_failure_example_is_explicit() -> None:
    _, output, trace = case("07-rule-tool-failure")

    assert output["terminal_reason"] == "tool_unavailable"
    assert any(
        step["tool"] == "check_rules" and step["result_kind"] == "error"
        for step in trace["review_steps"]
    )


def test_committed_budget_examples_are_incomplete_not_successful() -> None:
    _, model_output, _ = case("08-model-step-limit")
    _, tool_output, _ = case("09-tool-call-limit")

    assert model_output["status"] == "incomplete"
    assert model_output["terminal_reason"] == "model_step_limit_reached"
    assert tool_output["status"] == "incomplete"
    assert tool_output["terminal_reason"] == "tool_call_limit_reached"


def test_committed_multiple_missing_fields_are_machine_readable() -> None:
    _, output, _ = case("10-multiple-missing-fields")

    assert output["requested_fields"] == ["audience", "platform", "style"]
    assert output["requested_details"]


def test_committed_invalid_type_is_a_startup_validation_record() -> None:
    _, output, trace = case("11-invalid-input-type")

    assert output["status"] == "failed"
    assert output["error_code"] == "invalid_input"
    assert trace["startup_error"]["error_code"] == "invalid_input"
    assert trace["raw_events"] == []


def test_committed_unexpected_tool_exception_uses_graph_fallback() -> None:
    _, output, trace = case("12-unexpected-tool-exception")

    assert output["terminal_reason"] == "tool_unavailable"
    assert any(
        step["tool"] == "estimate_duration"
        and "Unexpected tool failure" in step["result_summary"]
        for step in trace["review_steps"]
    )

