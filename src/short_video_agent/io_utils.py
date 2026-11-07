"""UTF-8 JSON loading and writing helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from short_video_agent.schemas import BrandRule, Material, ScriptRequest


def _load_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_request(path: str | Path) -> ScriptRequest:
    return ScriptRequest.model_validate(_load_json(path))


def load_materials(path: str | Path) -> list[Material]:
    return TypeAdapter(list[Material]).validate_python(_load_json(path))


def load_rules(path: str | Path) -> list[BrandRule]:
    return TypeAdapter(list[BrandRule]).validate_python(_load_json(path))


def write_json(path: str | Path, payload: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

