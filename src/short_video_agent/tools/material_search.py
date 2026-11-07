"""Deterministic local material search tool."""

from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

from short_video_agent.schemas import Material, ResultKind, ToolResult


def _normalize(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()


class MaterialSearchTool:
    name = "search_materials"

    def __init__(
        self,
        materials: list[Material],
        *,
        failures_before_success: int = 0,
    ) -> None:
        self._materials = list(materials)
        self._remaining_failures = failures_before_success

    def invoke(self, arguments: dict[str, Any]) -> ToolResult:
        call_id = f"search-{uuid4().hex[:8]}"
        if self._remaining_failures > 0:
            self._remaining_failures -= 1
            return ToolResult(
                tool_name=self.name,
                call_id=call_id,
                ok=False,
                result_kind=ResultKind.ERROR,
                summary="Material storage is temporarily unavailable.",
                error_code="material_store_unavailable",
                retryable=True,
            )

        query = str(arguments.get("query", "")).strip()
        product_name = str(arguments.get("product_name") or "").strip()
        scope_ids = {str(item) for item in arguments.get("scope_ids", [])}
        try:
            limit = max(1, min(int(arguments.get("limit", 5)), 20))
        except (TypeError, ValueError):
            limit = 5

        normalized_query = _normalize(query)
        matches: list[tuple[int, Material, list[str]]] = []
        for material in self._materials:
            if scope_ids and material.material_id not in scope_ids:
                continue
            normalized_product = _normalize(product_name)
            official_match = normalized_product == _normalize(material.product_name)
            alias_match = normalized_product in {
                _normalize(alias) for alias in material.aliases
            }
            if product_name and not (official_match or alias_match):
                continue

            searchable_parts = [
                material.material_id,
                material.product_name,
                *material.aliases,
                material.title,
                *material.tags,
                *(fact.statement for fact in material.facts),
                *(keyword for fact in material.facts for keyword in fact.keywords),
            ]
            normalized_haystack = _normalize(" ".join(searchable_parts))
            matched_terms: list[str] = []
            score = 0
            if product_name:
                score += 5 if official_match else 3
            if normalized_query and normalized_query in normalized_haystack:
                score += 10
                matched_terms.append(query)
            for tag in material.tags:
                if _normalize(tag) and _normalize(tag) in normalized_query:
                    score += 3
                    matched_terms.append(tag)
            for fact in material.facts:
                for keyword in fact.keywords:
                    if _normalize(keyword) and _normalize(keyword) in normalized_query:
                        score += 2
                        matched_terms.append(keyword)
            if score > 0:
                matches.append((score, material, sorted(set(matched_terms))))

        matches.sort(key=lambda item: (-item[0], item[1].material_id))
        selected = matches[:limit]
        if not selected:
            return ToolResult(
                tool_name=self.name,
                call_id=call_id,
                ok=True,
                result_kind=ResultKind.EMPTY,
                summary=f"No materials matched query '{query}'.",
                data={"query": query, "matches": []},
            )

        payload = [
            {
                "material": material.model_dump(mode="json"),
                "score": score,
                "matched_terms": terms,
            }
            for score, material, terms in selected
        ]
        ids = [material.material_id for _, material, _ in selected]
        return ToolResult(
            tool_name=self.name,
            call_id=call_id,
            ok=True,
            result_kind=ResultKind.SUCCESS,
            summary=f"Matched {len(ids)} material(s): {', '.join(ids)}.",
            data={"query": query, "matches": payload},
        )

