"""Tests for schema export to schemas/ directory."""

import json
from pathlib import Path
from preference_lab.domain.export_schemas import MODELS_TO_EXPORT, export_all_schemas

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_exported_schemas_match_models():
    schemas_dir = REPO_ROOT / "schemas"
    assert schemas_dir.exists(), "schemas/ directory must exist"

    # Export again to ensure up to date
    exported = export_all_schemas(schemas_dir)
    assert len(exported) == len(MODELS_TO_EXPORT)

    for name, model_cls in MODELS_TO_EXPORT.items():
        schema_file = schemas_dir / f"{name}.schema.json"
        assert schema_file.exists(), f"Missing schema file: {schema_file}"
        with open(schema_file, "r", encoding="utf-8") as f:
            disk_schema = json.load(f)
        assert disk_schema == model_cls.model_json_schema()
