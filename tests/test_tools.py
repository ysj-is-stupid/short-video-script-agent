"""Unit tests for deterministic local business tools."""

from __future__ import annotations

from short_video_agent.schemas import Material, MaterialFact, Scene, ScriptDraft
from short_video_agent.tools import (
    DurationEstimatorTool,
    MaterialSearchTool,
    RuleCheckerTool,
)


def material() -> Material:
    return Material(
        material_id="P01",
        product_name="示例产品",
        title="字幕功能",
        facts=[
            MaterialFact(
                fact_id="P01-F01",
                statement="支持字幕",
                keywords=["字幕"],
            )
        ],
        tags=["字幕"],
    )


def test_material_search_distinguishes_match_and_empty() -> None:
    tool = MaterialSearchTool([material()])

    matched = tool.invoke({"query": "字幕功能"})
    empty = tool.invoke({"query": "自动翻译"})

    assert matched.ok is True
    assert matched.result_kind.value == "success"
    assert matched.data["matches"][0]["material"]["material_id"] == "P01"
    assert empty.ok is True
    assert empty.result_kind.value == "empty"


def test_material_search_accepts_declared_product_alias() -> None:
    source = material().model_copy(update={"aliases": ["示例"]})
    result = MaterialSearchTool([source]).invoke(
        {"query": "字幕", "product_name": "示例"}
    )

    assert result.result_kind.value == "success"
    assert result.data["matches"][0]["material"]["material_id"] == "P01"


def test_duration_estimator_rejects_over_target_script() -> None:
    draft = ScriptDraft(
        revision=1,
        title="长脚本",
        scenes=[
            Scene(
                scene_id="S01",
                visual="口播",
                narration="字幕功能介绍" * 30,
            )
        ],
    )

    result = DurationEstimatorTool().invoke(
        {"draft": draft.model_dump(mode="json"), "target_duration_seconds": 10}
    )

    assert result.ok is True
    assert result.result_kind.value == "rejected"
    assert result.data["report"]["within_limit"] is False


def test_rule_checker_rejects_unsupported_numeric_claim() -> None:
    source = material()
    draft = ScriptDraft(
        revision=1,
        title="无依据数据",
        scenes=[
            Scene(
                scene_id="S01",
                visual="展示字幕",
                narration="支持字幕，效率提升80%。",
                source_ids=["P01"],
                fact_ids=["P01-F01"],
            )
        ],
    )

    result = RuleCheckerTool([source]).invoke(
        {
            "draft": draft.model_dump(mode="json"),
            "retrieved_material_ids": ["P01"],
            "rules": [],
            "platform": "抖音",
        }
    )

    report = result.data["report"]
    assert report["passed"] is False
    assert any(
        violation["code"] == "unsupported_numeric_claim"
        for violation in report["violations"]
    )


def test_rule_checker_rejects_unsupported_non_numeric_claim_language() -> None:
    source = material()
    draft = ScriptDraft(
        revision=1,
        title="推断性宣传",
        scenes=[
            Scene(
                scene_id="S01",
                visual="展示字幕功能",
                narration="支持字幕，字幕别再手打，处理更省心，简洁好用。",
                source_ids=["P01"],
                fact_ids=["P01-F01"],
            )
        ],
    )

    result = RuleCheckerTool([source]).invoke(
        {
            "draft": draft.model_dump(mode="json"),
            "retrieved_material_ids": ["P01"],
            "rules": [],
            "platform": "抖音",
        }
    )

    violations = result.data["report"]["violations"]
    unsupported = [
        item for item in violations if item["code"] == "unsupported_claim_language"
    ]
    assert len(unsupported) == 1
    assert "手打" in unsupported[0]["message"]
    assert "省心" in unsupported[0]["message"]
    assert "好用" in unsupported[0]["message"]


def test_rule_checker_allows_claim_language_explicitly_present_in_fact() -> None:
    source = Material(
        material_id="P02",
        product_name="示例产品",
        title="自动字幕说明",
        facts=[
            MaterialFact(
                fact_id="P02-F01",
                statement="支持自动生成字幕，处理更省心",
                keywords=["字幕"],
            )
        ],
        tags=["字幕"],
    )
    draft = ScriptDraft(
        revision=1,
        title="有依据表达",
        scenes=[
            Scene(
                scene_id="S01",
                visual="展示字幕功能",
                narration="支持自动生成字幕，处理更省心。",
                source_ids=["P02"],
                fact_ids=["P02-F01"],
            )
        ],
    )

    result = RuleCheckerTool([source]).invoke(
        {
            "draft": draft.model_dump(mode="json"),
            "retrieved_material_ids": ["P02"],
            "rules": [],
            "platform": "抖音",
        }
    )

    assert result.data["report"]["passed"] is True


def test_rule_checker_ignores_step_numbers_but_rejects_effect_percentages() -> None:
    source = material()
    draft = ScriptDraft(
        revision=1,
        title="编号不是效果数据",
        scenes=[
            Scene(
                scene_id="S01",
                visual="展示第1步和第2步",
                narration="第1步打开字幕，第2步检查内容，效率提升80%。",
                source_ids=["P01"],
                fact_ids=["P01-F01"],
            )
        ],
    )

    result = RuleCheckerTool([source]).invoke(
        {
            "draft": draft.model_dump(mode="json"),
            "retrieved_material_ids": ["P01"],
            "rules": [],
            "platform": "抖音",
        }
    )

    messages = " ".join(
        item["message"] for item in result.data["report"]["violations"]
    )
    assert "80%" in messages
    assert "1" not in messages
    assert "2" not in messages


def test_rule_checker_automatically_allows_numbers_present_in_fact_text() -> None:
    source = Material(
        material_id="P03",
        product_name="示例产品",
        title="事实数字",
        facts=[
            MaterialFact(
                fact_id="P03-F01",
                statement="支持导出2种字幕格式",
                keywords=["字幕"],
            )
        ],
    )
    draft = ScriptDraft(
        revision=1,
        title="事实数字可追溯",
        scenes=[
            Scene(
                scene_id="S01",
                visual="展示字幕格式",
                narration="支持导出2种字幕格式。",
                source_ids=["P03"],
                fact_ids=["P03-F01"],
            )
        ],
    )

    result = RuleCheckerTool([source]).invoke(
        {
            "draft": draft.model_dump(mode="json"),
            "retrieved_material_ids": ["P03"],
            "rules": [],
            "platform": "抖音",
        }
    )

    assert result.data["report"]["passed"] is True


def test_rule_checker_does_not_treat_improvement_topic_as_a_claim() -> None:
    source = material()
    draft = ScriptDraft(
        revision=1,
        title="中性表达",
        scenes=[
            Scene(
                scene_id="S01",
                visual="展示字幕功能",
                narration="支持字幕，后续仍有提升空间，并不好用不是本片结论。",
                source_ids=["P01"],
                fact_ids=["P01-F01"],
            )
        ],
    )

    result = RuleCheckerTool([source]).invoke(
        {
            "draft": draft.model_dump(mode="json"),
            "retrieved_material_ids": ["P01"],
            "rules": [],
            "platform": "抖音",
        }
    )

    violations = result.data["report"]["violations"]
    assert not any(item["code"] == "unsupported_claim_language" for item in violations)

