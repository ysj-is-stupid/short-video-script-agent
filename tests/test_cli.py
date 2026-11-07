"""CLI integration test for the runnable offline path."""

from __future__ import annotations

import json
from pathlib import Path

from short_video_agent.cli import main
from short_video_agent.io_utils import write_json


def test_cli_writes_result_and_trace(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    materials_path = tmp_path / "materials.json"
    rules_path = tmp_path / "rules.json"
    output_path = tmp_path / "output.json"
    trace_path = tmp_path / "trace.json"
    write_json(
        request_path,
        {
            "topic": "字幕功能",
            "audience": "短视频创作者",
            "platform": "抖音",
            "target_duration_seconds": 30,
            "style": "简洁",
            "product_name": "示例产品",
        },
    )
    write_json(
        materials_path,
        [
            {
                "material_id": "P01",
                "product_name": "示例产品",
                "title": "字幕功能",
                "facts": [
                    {
                        "fact_id": "P01-F01",
                        "statement": "支持字幕",
                        "keywords": ["字幕"],
                        "allowed_numbers": [],
                    }
                ],
                "tags": ["字幕"],
            }
        ],
    )
    write_json(rules_path, [])

    exit_code = main(
        [
            "run",
            "--input",
            str(request_path),
            "--materials",
            str(materials_path),
            "--rules",
            str(rules_path),
            "--output",
            str(output_path),
            "--trace",
            str(trace_path),
            "--model-mode",
            "mock",
        ]
    )

    output = json.loads(output_path.read_text(encoding="utf-8"))
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert output["status"] == "completed"
    assert output["trace_file"] == str(trace_path)
    assert trace["model_mode"] == "mock"
    assert trace["mock_boundary"]
    assert trace["trace_schema_version"] == "2.0"
    assert trace["model_metadata"]["provider"] == "scripted_mock"
    assert trace["review_steps"][0]["next_action"] == "estimate_duration"


def test_cli_unexpected_error_returns_five_without_leaking_message(
    tmp_path: Path, monkeypatch: object
) -> None:
    output_path = tmp_path / "internal-error-output.json"
    trace_path = tmp_path / "internal-error-trace.json"

    def raise_internal_error(_: str) -> object:
        raise RuntimeError("sensitive-internal-detail")

    monkeypatch.setattr(
        "short_video_agent.cli.load_request",
        raise_internal_error,
    )
    exit_code = main(
        [
            "run",
            "--input",
            str(tmp_path / "input.json"),
            "--materials",
            str(tmp_path / "materials.json"),
            "--rules",
            str(tmp_path / "rules.json"),
            "--model-mode",
            "mock",
            "--output",
            str(output_path),
            "--trace",
            str(trace_path),
        ]
    )

    output = json.loads(output_path.read_text(encoding="utf-8"))
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    serialized = json.dumps({"output": output, "trace": trace})
    assert exit_code == 5
    assert output["status"] == "failed"
    assert output["error_code"] == "internal_error"
    assert "RuntimeError" in output["message"]
    assert "sensitive-internal-detail" not in serialized
    assert output["trace_file"] == str(trace_path)
    assert trace["startup_error"]["error_code"] == "internal_error"


def test_cli_known_input_error_still_returns_two(tmp_path: Path) -> None:
    output_path = tmp_path / "input-error-output.json"
    exit_code = main(
        [
            "run",
            "--input",
            str(tmp_path / "missing-input.json"),
            "--materials",
            str(tmp_path / "materials.json"),
            "--rules",
            str(tmp_path / "rules.json"),
            "--model-mode",
            "mock",
            "--output",
            str(output_path),
        ]
    )

    output = json.loads(output_path.read_text(encoding="utf-8"))
    assert exit_code == 2
    assert output["status"] == "failed"
    assert output["error_code"] == "invalid_input"

