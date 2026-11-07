"""Reproducible narration/subtitle duration estimation."""

from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

from short_video_agent.drafting import canonicalize_draft
from short_video_agent.schemas import (
    DurationReport,
    ResultKind,
    SceneDuration,
    ScriptDraft,
    ToolResult,
)


class DurationEstimatorTool:
    name = "estimate_duration"

    def __init__(
        self,
        *,
        chinese_chars_per_second: float = 4.0,
        english_words_per_minute: float = 150.0,
        transition_seconds: float = 0.5,
        minimum_scene_seconds: float = 1.0,
    ) -> None:
        self.chinese_chars_per_second = chinese_chars_per_second
        self.english_words_per_minute = english_words_per_minute
        self.transition_seconds = transition_seconds
        self.minimum_scene_seconds = minimum_scene_seconds

    def _estimate_text(self, text: str) -> float:
        chinese_count = len(re.findall(r"[\u3400-\u9fff]", text))
        english_words = len(re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", text))
        other_readable = len(re.findall(r"\d+(?:\.\d+)?%?", text))
        seconds = chinese_count / self.chinese_chars_per_second
        seconds += english_words / (self.english_words_per_minute / 60.0)
        seconds += other_readable * 0.4
        return seconds

    def invoke(self, arguments: dict[str, Any]) -> ToolResult:
        call_id = f"duration-{uuid4().hex[:8]}"
        try:
            draft = canonicalize_draft(ScriptDraft.model_validate(arguments["draft"]))
            target = int(arguments["target_duration_seconds"])
        except (KeyError, TypeError, ValueError) as exc:
            return ToolResult(
                tool_name=self.name,
                call_id=call_id,
                ok=False,
                result_kind=ResultKind.ERROR,
                summary=f"Invalid duration arguments: {exc}",
                error_code="invalid_duration_arguments",
                retryable=False,
            )

        scene_durations: list[SceneDuration] = []
        for scene in draft.scenes:
            text = scene.narration or scene.subtitle or ""
            seconds = max(self._estimate_text(text), self.minimum_scene_seconds)
            seconds += self.transition_seconds
            scene_durations.append(
                SceneDuration(
                    scene_id=scene.scene_id,
                    estimated_seconds=round(seconds, 1),
                )
            )

        total = round(sum(item.estimated_seconds for item in scene_durations), 1)
        report = DurationReport(
            draft_revision=draft.revision,
            draft_fingerprint=draft.fingerprint or "",
            scene_durations=scene_durations,
            total_seconds=total,
            target_seconds=target,
            over_by_seconds=round(max(0.0, total - target), 1),
            within_limit=total <= target,
            estimation_method=(
                f"zh={self.chinese_chars_per_second} chars/s; "
                f"en={self.english_words_per_minute} words/min; "
                f"transition={self.transition_seconds}s/scene"
            ),
        )
        return ToolResult(
            tool_name=self.name,
            call_id=call_id,
            ok=True,
            result_kind=(
                ResultKind.SUCCESS if report.within_limit else ResultKind.REJECTED
            ),
            summary=(
                f"Estimated {total:.1f}s for target {target}s; "
                f"within_limit={str(report.within_limit).lower()}."
            ),
            data={"report": report.model_dump(mode="json")},
        )

