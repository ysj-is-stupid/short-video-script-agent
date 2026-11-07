"""Deterministic source and brand-rule checks."""

from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

from short_video_agent.drafting import canonicalize_draft
from short_video_agent.schemas import (
    BrandRule,
    Material,
    ResultKind,
    RuleReport,
    RuleViolation,
    ScriptDraft,
    Severity,
    ToolResult,
)


RISKY_CLAIM_PATTERNS = {
    "自动能力": re.compile(r"自动(?:生成|识别|添加|处理|完成|剪辑|同步)"),
    "智能能力": re.compile(r"智能(?:生成|识别|处理|剪辑|推荐)"),
    "一键能力": re.compile(r"一键(?:生成|完成|处理|添加|发布)"),
    "免手动": re.compile(r"(?:无需|不用|免去|别再)(?:手动|手打)|手打"),
    "省时": re.compile(r"(?<!不)省时"),
    "省心": re.compile(r"(?<!不)省心"),
    "效率效果": re.compile(r"高效|提效|效率提升|提升效率|显著提升"),
    "比较优势": re.compile(r"更快|更方便|更简单"),
    "易用性": re.compile(r"(?<!不)(?:好用|易用)"),
    "帮助承诺": re.compile(r"帮你(?:完成|生成|提高|提升|节省)"),
}


def _claim_numbers(text: str) -> set[str]:
    """Extract claim-like numbers while excluding ordinals and step labels."""

    numbers: set[str] = set()
    for match in re.finditer(r"\d+(?:\.\d+)?%?", text):
        before = text[match.start() - 1 : match.start()]
        after = text[match.end() : match.end() + 1]
        if before == "第" or after in {"步", "号", "幕", "镜", "段", "页", "集"}:
            continue
        numbers.add(match.group(0))
    return numbers


def _claim_terms(text: str) -> set[str]:
    return {
        match.group(0)
        for pattern in RISKY_CLAIM_PATTERNS.values()
        for match in pattern.finditer(text)
    }


class RuleCheckerTool:
    name = "check_rules"

    def __init__(self, materials: list[Material]) -> None:
        self._materials = {item.material_id: item for item in materials}

    def invoke(self, arguments: dict[str, Any]) -> ToolResult:
        call_id = f"rules-{uuid4().hex[:8]}"
        try:
            draft = canonicalize_draft(ScriptDraft.model_validate(arguments["draft"]))
            rules = [BrandRule.model_validate(item) for item in arguments.get("rules", [])]
            retrieved_ids = {
                str(item) for item in arguments.get("retrieved_material_ids", [])
            }
            platform = str(arguments.get("platform") or "")
        except (KeyError, TypeError, ValueError) as exc:
            return ToolResult(
                tool_name=self.name,
                call_id=call_id,
                ok=False,
                result_kind=ResultKind.ERROR,
                summary=f"Invalid rule-check arguments: {exc}",
                error_code="invalid_rule_arguments",
                retryable=False,
            )

        violations: list[RuleViolation] = []
        warnings: list[RuleViolation] = []
        checked_source_ids: set[str] = set()

        full_text = " ".join(
            part
            for scene in draft.scenes
            for part in (scene.visual, scene.narration or "", scene.subtitle or "")
        )

        for scene in draft.scenes:
            scene_text = " ".join(
                [scene.visual, scene.narration or "", scene.subtitle or ""]
            )
            fact_lookup: dict[str, tuple[str, set[str], str]] = {}
            for source_id in scene.source_ids:
                checked_source_ids.add(source_id)
                material = self._materials.get(source_id)
                if material is None or source_id not in retrieved_ids:
                    violations.append(
                        RuleViolation(
                            code="unknown_or_unretrieved_source",
                            severity=Severity.ERROR,
                            scene_id=scene.scene_id,
                            message=f"Source '{source_id}' was not retrieved for this run.",
                            related_source_ids=[source_id],
                        )
                    )
                    continue
                for fact in material.facts:
                    fact_lookup[fact.fact_id] = (
                        source_id,
                        set(fact.allowed_numbers),
                        fact.statement,
                    )

            if not scene.source_ids:
                unsupported_source_terms = sorted(
                    {
                        material.product_name
                        for material in self._materials.values()
                        if material.product_name in scene_text
                    }
                    | {
                        fact.statement
                        for material in self._materials.values()
                        for fact in material.facts
                        if fact.statement in scene_text
                    }
                )
                if unsupported_source_terms:
                    violations.append(
                        RuleViolation(
                            code="product_claim_missing_source",
                            severity=Severity.ERROR,
                            scene_id=scene.scene_id,
                            message=(
                                "Product claim text has no cited source: "
                                + ", ".join(unsupported_source_terms)
                            ),
                        )
                    )

            if scene.source_ids and not scene.fact_ids:
                violations.append(
                    RuleViolation(
                        code="source_without_fact",
                        severity=Severity.ERROR,
                        scene_id=scene.scene_id,
                        message="A sourced product scene must cite at least one fact ID.",
                        related_source_ids=scene.source_ids,
                    )
                )

            allowed_numbers: set[str] = set()
            approved_claim_texts: list[str] = []
            for fact_id in scene.fact_ids:
                source_fact = fact_lookup.get(fact_id)
                if source_fact is None:
                    violations.append(
                        RuleViolation(
                            code="unknown_or_mismatched_fact",
                            severity=Severity.ERROR,
                            scene_id=scene.scene_id,
                            message=f"Fact '{fact_id}' does not belong to a cited source.",
                            related_source_ids=scene.source_ids,
                            related_fact_ids=[fact_id],
                        )
                    )
                else:
                    allowed_numbers.update(source_fact[1])
                    allowed_numbers.update(_claim_numbers(source_fact[2]))
                    approved_claim_texts.append(source_fact[2])

            observed_numbers = _claim_numbers(scene_text) if scene.fact_ids else set()
            unsupported_numbers = sorted(observed_numbers - allowed_numbers)
            if unsupported_numbers:
                violations.append(
                    RuleViolation(
                        code="unsupported_numeric_claim",
                        severity=Severity.ERROR,
                        scene_id=scene.scene_id,
                        message=(
                            "Numbers are not supported by cited material facts: "
                            + ", ".join(unsupported_numbers)
                        ),
                        related_source_ids=scene.source_ids,
                        related_fact_ids=scene.fact_ids,
                    )
                )

            approved_text = " ".join(approved_claim_texts)
            unsupported_claim_terms = sorted(
                _claim_terms(scene_text) - _claim_terms(approved_text)
            )
            if unsupported_claim_terms:
                violations.append(
                    RuleViolation(
                        code="unsupported_claim_language",
                        severity=Severity.ERROR,
                        scene_id=scene.scene_id,
                        message=(
                            "Claim language is not supported by cited fact text: "
                            + ", ".join(unsupported_claim_terms)
                        ),
                        related_source_ids=scene.source_ids,
                        related_fact_ids=scene.fact_ids,
                    )
                )

        for rule in rules:
            if rule.applies_to_platforms and platform not in rule.applies_to_platforms:
                continue
            target = violations if rule.severity is Severity.ERROR else warnings
            for term in rule.forbidden_terms:
                if term and term in full_text:
                    target.append(
                        RuleViolation(
                            code="forbidden_term",
                            severity=rule.severity,
                            message=f"Forbidden term found under {rule.rule_id}: {term}",
                        )
                    )
            for term in rule.required_terms:
                if term and term not in full_text:
                    target.append(
                        RuleViolation(
                            code="required_term_missing",
                            severity=rule.severity,
                            message=f"Required term missing under {rule.rule_id}: {term}",
                        )
                    )

        report = RuleReport(
            draft_revision=draft.revision,
            draft_fingerprint=draft.fingerprint or "",
            passed=not violations,
            violations=violations,
            warnings=warnings,
            checked_source_ids=sorted(checked_source_ids),
        )
        violation_codes = sorted({item.code for item in violations})
        code_summary = ",".join(violation_codes) if violation_codes else "none"
        return ToolResult(
            tool_name=self.name,
            call_id=call_id,
            ok=True,
            result_kind=(ResultKind.SUCCESS if report.passed else ResultKind.REJECTED),
            summary=(
                f"Rule check passed={str(report.passed).lower()}; "
                f"errors={len(violations)}; warnings={len(warnings)}; "
                f"codes={code_summary}."
            ),
            data={"report": report.model_dump(mode="json")},
        )

