"""Export Pydantic domain models to JSON Schemas in schemas/ according to PREFERENCE_LAB_SPEC.md."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Type
from pydantic import BaseModel

from preference_lab.domain.schemas import (
    ActionSpec,
    DecisionRecord,
    Event,
    Instrument,
    Outcome,
    Session,
    Trial,
    TrialPrivate,
)

MODELS_TO_EXPORT: dict[str, Type[BaseModel]] = {
    "ActionSpec": ActionSpec,
    "Instrument": Instrument,
    "Trial": Trial,
    "TrialPrivate": TrialPrivate,
    "DecisionRecord": DecisionRecord,
    "Event": Event,
    "Outcome": Outcome,
    "Session": Session,
}


def export_all_schemas(output_dir: Path | str | None = None) -> list[Path]:
    """Export JSON schemas for all core domain models."""
    if output_dir is None:
        # Search upward for repo root containing PREFERENCE_LAB_SPEC.md
        cur = Path(__file__).resolve().parent
        while cur.parent != cur and not (cur / "PREFERENCE_LAB_SPEC.md").exists():
            cur = cur.parent
        repo_root = cur
        output_dir = repo_root / "schemas"
    else:
        output_dir = Path(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)
    exported_files = []

    for name, model_cls in MODELS_TO_EXPORT.items():
        schema_dict = model_cls.model_json_schema()
        target_path = output_dir / f"{name}.schema.json"
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(schema_dict, f, indent=2, ensure_ascii=False)
            f.write("\n")
        exported_files.append(target_path)

    return exported_files


if __name__ == "__main__":
    files = export_all_schemas()
    print(f"Exported {len(files)} JSON schemas to schemas/")
