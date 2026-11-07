"""Helpers for canonical script revisions and fingerprints."""

from __future__ import annotations

import hashlib
import json

from short_video_agent.schemas import Scene, ScriptDraft


def compute_draft_fingerprint(draft: ScriptDraft) -> str:
    """Hash authored content while excluding tool-computed duration fields."""

    payload = {
        "title": draft.title.strip(),
        "scenes": [
            {
                "scene_id": scene.scene_id,
                "visual": scene.visual.strip(),
                "narration": (scene.narration or "").strip(),
                "subtitle": (scene.subtitle or "").strip(),
                "source_ids": sorted(scene.source_ids),
                "fact_ids": sorted(scene.fact_ids),
            }
            for scene in draft.scenes
        ],
    }
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def canonicalize_draft(draft: ScriptDraft) -> ScriptDraft:
    """Discard model-provided estimates and attach a trusted fingerprint."""

    clean_scenes = [
        Scene(
            scene_id=scene.scene_id,
            visual=scene.visual,
            narration=scene.narration,
            subtitle=scene.subtitle,
            source_ids=scene.source_ids,
            fact_ids=scene.fact_ids,
            estimated_seconds=None,
        )
        for scene in draft.scenes
    ]
    clean = ScriptDraft(
        revision=draft.revision,
        title=draft.title,
        scenes=clean_scenes,
    )
    return clean.model_copy(update={"fingerprint": compute_draft_fingerprint(clean)})

