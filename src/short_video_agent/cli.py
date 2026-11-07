"""Command-line entry point for offline and live Agent runs."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from pydantic import ValidationError

from short_video_agent import __version__
from short_video_agent.config import AppConfig
from short_video_agent.errors import AppError
from short_video_agent.io_utils import (
    load_materials,
    load_request,
    load_rules,
    write_json,
)
from short_video_agent.model import LiveModelAdapter, ScriptedMockAdapter
from short_video_agent.runtime import run_agent
from short_video_agent.schemas import TaskStatus
from short_video_agent.trace import build_trace_payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="short-video-agent",
        description="Generate source-grounded, duration-constrained short-video scripts.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    subparsers = parser.add_subparsers(dest="command")
    run_parser = subparsers.add_parser("run", help="Run the LangGraph Agent.")
    run_parser.add_argument("--input", required=True, help="Request JSON file.")
    run_parser.add_argument("--materials", required=True, help="Materials JSON file.")
    run_parser.add_argument("--rules", required=True, help="Brand rules JSON file.")
    run_parser.add_argument("--output", help="Write AgentResult JSON to this path.")
    run_parser.add_argument("--trace", help="Write trace JSON to this path.")
    run_parser.add_argument(
        "--model-mode",
        choices=("mock", "live"),
        help="Override MODEL_MODE from the environment.",
    )
    run_parser.add_argument(
        "--simulate-duration-fault",
        choices=("error", "timeout", "exception"),
        help="Inject a deterministic duration-tool fault for acceptance tests.",
    )
    run_parser.add_argument(
        "--simulate-rule-fault",
        choices=("error", "timeout", "exception"),
        help="Inject a deterministic rule-tool fault for acceptance tests.",
    )
    run_parser.add_argument("--max-model-steps", type=int)
    run_parser.add_argument("--max-tool-calls", type=int)
    run_parser.add_argument(
        "--scenario",
        default="duration_revision",
        help="Offline Mock scenario name.",
    )
    run_parser.add_argument(
        "--simulate-search-failures",
        type=int,
        default=0,
        help="Return this many retryable material-search errors first.",
    )
    return parser


def _exit_code(status: TaskStatus) -> int:
    if status in {TaskStatus.COMPLETED, TaskStatus.NEEDS_INPUT}:
        return 0
    if status is TaskStatus.INCOMPLETE:
        return 3
    return 4


def _emit_error(
    args: argparse.Namespace,
    *,
    code: str,
    message: str,
    model_mode: str,
    model_metadata: dict[str, object] | None = None,
) -> None:
    payload: dict[str, object] = {
        "status": "failed",
        "error_code": code,
        "message": message,
    }
    if args.trace:
        trace_path = str(Path(args.trace))
        trace_payload = build_trace_payload(
            [],
            model_mode=model_mode,
            scenario=args.scenario if model_mode == "mock" else None,
            model_metadata=model_metadata,
        )
        trace_payload["startup_error"] = dict(payload)
        try:
            write_json(trace_path, trace_payload)
            payload["trace_file"] = trace_path
        except Exception as trace_error:
            payload["trace_write_error"] = type(trace_error).__name__

    if args.output:
        try:
            write_json(args.output, payload)
            return
        except Exception as output_error:
            payload["output_write_error"] = type(output_error).__name__

    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0

    config: AppConfig | None = None
    adapter: LiveModelAdapter | ScriptedMockAdapter | None = None
    try:
        config = AppConfig.from_env()
        if args.model_mode:
            config = replace(config, model_mode=args.model_mode)
        if args.max_model_steps is not None:
            if args.max_model_steps <= 0:
                parser.error("--max-model-steps must be greater than zero")
            config = replace(config, max_model_steps=args.max_model_steps)
        if args.max_tool_calls is not None:
            if args.max_tool_calls <= 0:
                parser.error("--max-tool-calls must be greater than zero")
            config = replace(config, max_tool_calls=args.max_tool_calls)
        request = load_request(args.input)
        materials = load_materials(args.materials)
        rules = load_rules(args.rules)
        if config.model_mode == "live":
            adapter = LiveModelAdapter(
                api_key=config.model_api_key,
                model=config.model_name,
                provider=config.model_provider,
                base_url=config.model_base_url,
                timeout_seconds=config.model_timeout_seconds,
            )
        else:
            adapter = ScriptedMockAdapter(args.scenario)

        outcome = run_agent(
            request=request,
            materials=materials,
            rules=rules,
            model_adapter=adapter,
            config=config,
            search_failures_before_success=max(0, args.simulate_search_failures),
            duration_fault=args.simulate_duration_fault,
            rule_fault=args.simulate_rule_fault,
        )
        result = outcome.result
        if args.trace:
            trace_path = str(Path(args.trace))
            write_json(
                trace_path,
                build_trace_payload(
                    outcome.trace_events,
                    model_mode=adapter.mode,
                    scenario=args.scenario if adapter.mode == "mock" else None,
                    model_metadata=getattr(adapter, "trace_metadata", None),
                ),
            )
            result = result.model_copy(update={"trace_file": trace_path})

        payload = result.model_dump(mode="json")
        if args.output:
            write_json(args.output, payload)
        else:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        return _exit_code(result.status)
    except (AppError, ValidationError, OSError, json.JSONDecodeError) as exc:
        model_mode = (
            adapter.mode
            if adapter is not None
            else config.model_mode
            if config is not None
            else args.model_mode or "unknown"
        )
        _emit_error(
            args,
            code=getattr(exc, "code", "invalid_input"),
            message=str(exc),
            model_mode=model_mode,
            model_metadata=(
                dict(getattr(adapter, "trace_metadata", {}))
                if adapter is not None
                else None
            ),
        )
        return 2
    except Exception as exc:
        model_mode = (
            adapter.mode
            if adapter is not None
            else config.model_mode
            if config is not None
            else args.model_mode or "unknown"
        )
        _emit_error(
            args,
            code="internal_error",
            message=f"Unhandled internal error: {type(exc).__name__}.",
            model_mode=model_mode,
            model_metadata=(
                dict(getattr(adapter, "trace_metadata", {}))
                if adapter is not None
                else None
            ),
        )
        return 5

