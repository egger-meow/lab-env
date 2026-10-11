"""Tests for formal Instrument validation pipeline according to PREFERENCE_LAB_SPEC.md."""

import pytest
from preference_lab.domain.schemas import ActionSpec, Instrument
from preference_lab.domain.validation import validate_instrument


def test_empty_action_specs_rejected():
    inst = Instrument(
        instrument_id="inst_001",
        instrument_version="0.1.0",
        environment_id="puzzle_hints",
        item_id="p1",
        template_id="t1",
        public_stimulus={},
        action_specs=[],
    )
    with pytest.raises(ValueError, match="action_specs cannot be empty"):
        validate_instrument(inst)


def test_duplicate_action_ids_rejected():
    inst = Instrument(
        instrument_id="inst_001",
        instrument_version="0.1.0",
        environment_id="puzzle_hints",
        item_id="p1",
        template_id="t1",
        public_stimulus={},
        action_specs=[
            ActionSpec(action_id="continue", label="A", description=""),
            ActionSpec(action_id="continue", label="B", description=""),
        ],
    )
    with pytest.raises(ValueError, match="Duplicate action_id"):
        validate_instrument(inst)


def test_puzzle_missing_clues_rejected():
    inst = Instrument(
        instrument_id="inst_001",
        instrument_version="0.1.0",
        environment_id="puzzle_hints",
        item_id="p1",
        template_id="t1",
        public_stimulus={"num_positions": 4, "items": ["a", "b", "c", "d"], "clues": []},
        action_specs=[
            ActionSpec(action_id="continue", label="", description=""),
            ActionSpec(action_id="hint", label="", description=""),
            ActionSpec(action_id="next_step", label="", description=""),
            ActionSpec(action_id="solution", label="", description=""),
        ],
        private_data={
            "expected_solution": ["a", "b", "c", "d"],
            "hint_text": "hint",
            "source_clue_ids": ["c1"],
        },
    )
    # Fails because source_clue_ids c1 doesn't exist in empty clues
    with pytest.raises(ValueError):
        validate_instrument(inst)


def test_bret_options_count_must_be_4():
    inst = Instrument(
        instrument_id="inst_001",
        instrument_version="0.1.0",
        environment_id="bret_discrete",
        item_id="b1",
        template_id="t1",
        public_stimulus={
            "num_boxes": 100,
            "reward_per_box": 1,
            "options": [
                {"action_id": "c0", "k": 0, "label": ""},
                {"action_id": "c10", "k": 10, "label": ""},
            ],
        },
        action_specs=[
            ActionSpec(action_id="c0", label="", description=""),
            ActionSpec(action_id="c10", label="", description=""),
        ],
    )
    with pytest.raises(ValueError, match="BRET must have exactly 4 options"):
        validate_instrument(inst)


def test_bret_options_must_contain_k_zero():
    inst = Instrument(
        instrument_id="inst_001",
        instrument_version="0.1.0",
        environment_id="bret_discrete",
        item_id="b1",
        template_id="t1",
        public_stimulus={
            "num_boxes": 100,
            "reward_per_box": 1,
            "options": [
                {"action_id": "c10", "k": 10, "label": ""},
                {"action_id": "c20", "k": 20, "label": ""},
                {"action_id": "c30", "k": 30, "label": ""},
                {"action_id": "c40", "k": 40, "label": ""},
            ],
        },
        action_specs=[
            ActionSpec(action_id="c10", label="", description=""),
            ActionSpec(action_id="c20", label="", description=""),
            ActionSpec(action_id="c30", label="", description=""),
            ActionSpec(action_id="c40", label="", description=""),
        ],
    )
    with pytest.raises(ValueError, match="must include a k=0"):
        validate_instrument(inst)


def test_bret_tutorial_requires_structure():
    inst = Instrument(
        instrument_id="inst_001",
        instrument_version="0.1.0",
        environment_id="bret_discrete",
        item_id="b1",
        template_id="t1",
        public_stimulus={
            "num_boxes": 10,
            "reward_per_box": 1,
            "options": [
                {"action_id": "c0", "k": 0, "label": ""},
                {"action_id": "c2", "k": 2, "label": ""},
                {"action_id": "c4", "k": 4, "label": ""},
                {"action_id": "c6", "k": 6, "label": ""},
            ],
        },
        action_specs=[
            ActionSpec(action_id="c0", label="", description=""),
            ActionSpec(action_id="c2", label="", description=""),
            ActionSpec(action_id="c4", label="", description=""),
            ActionSpec(action_id="c6", label="", description=""),
        ],
        private_data={"is_tutorial": True},  # Missing tutorial_type
    )
    with pytest.raises(ValueError, match="must specify tutorial_type"):
        validate_instrument(inst)
