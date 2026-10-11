"""Comprehensive test validating all on-disk instruments and protocols for M1."""

import json
from pathlib import Path
import pytest

from preference_lab.domain.canonical import sha256_canonical_json
from preference_lab.domain.schemas import Instrument
from preference_lab.domain.puzzle import (
    PuzzlePublicStimulus,
    PuzzlePrivateData,
    validate_puzzle_stimulus,
)
from preference_lab.domain.bret import (
    BretPublicStimulus,
    get_bret_action_stats,
    validate_bret_params,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_puzzle_fixtures_integrity_and_uniqueness():
    puzzle_dir = REPO_ROOT / "instruments" / "puzzle_hints" / "v001"
    assert puzzle_dir.exists(), f"Path not found: {puzzle_dir}"

    fixture_files = list(puzzle_dir.glob("*.json"))
    assert len(fixture_files) == 6, f"Expected 6 puzzle fixtures (2 practice + 4 pilot), found {len(fixture_files)}"

    template_ids = set()

    for fpath in fixture_files:
        with open(fpath, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        # 1. Pydantic schema validation
        instrument = Instrument.model_validate(raw_data)
        assert instrument.environment_id == "puzzle_hints"
        template_ids.add(instrument.template_id)

        # 2. Canonical hash must succeed
        h = sha256_canonical_json(raw_data)
        assert len(h) == 64

        # 3. Domain validation (must have exactly one unique solution matching expected_solution)
        stimulus = PuzzlePublicStimulus.model_validate(instrument.public_stimulus)
        private_data = PuzzlePrivateData.model_validate(instrument.private_data)
        validate_puzzle_stimulus(stimulus, private_data)

    # Spec Section 5.5: 至少 3 種線索結構 template_id
    assert len(template_ids) >= 3, f"Expected at least 3 template_ids, found {len(template_ids)}: {template_ids}"


def test_bret_fixtures_integrity_and_math():
    bret_dir = REPO_ROOT / "instruments" / "bret_discrete" / "v001"
    assert bret_dir.exists(), f"Path not found: {bret_dir}"

    fixture_files = list(bret_dir.glob("*.json"))
    assert len(fixture_files) == 6, f"Expected 6 BRET fixtures (2 tutorial + 4 pilot), found {len(fixture_files)}"

    for fpath in fixture_files:
        with open(fpath, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        # 1. Pydantic schema validation
        instrument = Instrument.model_validate(raw_data)
        assert instrument.environment_id == "bret_discrete"

        # 2. Canonical hash
        h = sha256_canonical_json(raw_data)
        assert len(h) == 64

        # 3. Stimulus & options validation
        stimulus = BretPublicStimulus.model_validate(instrument.public_stimulus)
        assert len(stimulus.options) == 4, "Every BRET round must have 4 action options"

        # Check options k values and ensure collect_0 is present
        k_values = [opt.k for opt in stimulus.options]
        assert 0 in k_values, f"k=0 option must be present in {fpath.name}"

        for opt in stimulus.options:
            validate_bret_params(stimulus.num_boxes, stimulus.reward_per_box, opt.k)
            stats = get_bret_action_stats(stimulus.num_boxes, stimulus.reward_per_box, opt.k)
            assert stats.hit_probability == opt.k / stimulus.num_boxes


def test_protocol_references_existing_items():
    proto_path = REPO_ROOT / "protocols" / "pilot_v001.json"
    assert proto_path.exists()

    with open(proto_path, "r", encoding="utf-8") as f:
        proto = json.load(f)

    assert proto["protocol_id"] == "pilot_v001"
    assert proto["active_play_ms_threshold"] == 45000

    puzzle_items = set()
    for f in (REPO_ROOT / "instruments" / "puzzle_hints" / "v001").glob("*.json"):
        with open(f, "r", encoding="utf-8") as pf:
            puzzle_items.add(json.load(pf)["item_id"])

    bret_items = set()
    for f in (REPO_ROOT / "instruments" / "bret_discrete" / "v001").glob("*.json"):
        with open(f, "r", encoding="utf-8") as bf:
            bret_items.add(json.load(bf)["item_id"])

    for item in proto["environments"]["puzzle_hints"]["practice_items"]:
        assert item in puzzle_items, f"Missing puzzle item: {item}"
    for item in proto["environments"]["puzzle_hints"]["pilot_items"]:
        assert item in puzzle_items, f"Missing puzzle item: {item}"

    for item in proto["environments"]["bret_discrete"]["practice_items"]:
        assert item in bret_items, f"Missing BRET item: {item}"
    for item in proto["environments"]["bret_discrete"]["pilot_items"]:
        assert item in bret_items, f"Missing BRET item: {item}"
