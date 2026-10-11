"""Unified formal loading and runtime validation for Preference Lab."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from preference_lab.domain.bret import BretPublicStimulus, validate_bret_params
from preference_lab.domain.puzzle import (
    PuzzlePrivateData,
    PuzzlePublicStimulus,
    validate_puzzle_stimulus,
)
from preference_lab.domain.schemas import DecisionRecord, Instrument


def validate_decision_record(
    record: DecisionRecord,
    valid_action_ids: set[str] | list[str],
) -> None:
    """Validate a DecisionRecord against the allowable actions of the trial.

    Rules from PREFERENCE_LAB_SPEC.md (Section 7.1):
    1. deliberation_ms must be >= 0.
    2. acceptable_by_action must explicitly cover every valid action (no missing, no extra).
    3. selected_action_id must be in valid_action_ids.
    4. preferred_action_ids, if provided, must be a non-empty subset of valid_action_ids
       and must contain selected_action_id.
    5. If acceptable_by_action for selected_action_id is 'no',
       selection_acceptability_override must be True.
    """
    valid_set = set(valid_action_ids)
    if not valid_set:
        raise ValueError("valid_action_ids cannot be empty")

    if record.deliberation_ms < 0:
        raise ValueError(
            f"deliberation_ms cannot be negative, got {record.deliberation_ms}"
        )

    action_keys = set(record.acceptable_by_action.keys())
    if action_keys != valid_set:
        missing = valid_set - action_keys
        extra = action_keys - valid_set
        raise ValueError(
            f"acceptable_by_action must cover all valid actions exactly. "
            f"Missing: {missing}, Extra: {extra}"
        )

    for action_id, rating in record.acceptable_by_action.items():
        if rating not in ("yes", "no", "unsure"):
            raise ValueError(
                f"Invalid acceptability rating '{rating}' for action '{action_id}'. "
                f"Must be 'yes', 'no', or 'unsure'."
            )

    if record.selected_action_id not in valid_set:
        raise ValueError(
            f"selected_action_id '{record.selected_action_id}' is not in valid actions: {valid_set}"
        )

    if record.preferred_action_ids is not None:
        if len(record.preferred_action_ids) == 0:
            raise ValueError("preferred_action_ids if specified cannot be empty")
        pref_set = set(record.preferred_action_ids)
        if not pref_set.issubset(valid_set):
            raise ValueError(
                f"preferred_action_ids contains invalid actions: {pref_set - valid_set}"
            )
        if record.selected_action_id not in pref_set:
            raise ValueError(
                f"preferred_action_ids must include selected_action_id '{record.selected_action_id}'"
            )

    selected_rating = record.acceptable_by_action[record.selected_action_id]
    if selected_rating == "no" and not record.selection_acceptability_override:
        raise ValueError(
            f"selected_action_id '{record.selected_action_id}' was rated 'no', "
            f"so selection_acceptability_override must be True"
        )


def validate_instrument(instrument: Instrument) -> Instrument:
    """Strictly validate an instrument before formal loading.

    Checks:
    - action_specs non-empty, action_ids unique.
    - Puzzle: validates public stimulus, clues, expected solution, uniqueness of solution,
      and verifies action_specs matches the 4 standard actions.
    - BRET: validates stimulus (N, r), 4 options with valid k in [0, N], includes k=0,
      and action_specs align with options.
    - Validates tutorial structure if marked tutorial.

    On success, upgrades author_status to 'engine_validated' (unless already human_reviewed).
    """
    if not instrument.action_specs:
        raise ValueError("Instrument action_specs cannot be empty")

    action_ids = [spec.action_id for spec in instrument.action_specs]
    if len(action_ids) != len(set(action_ids)):
        raise ValueError(f"Duplicate action_id in action_specs: {action_ids}")

    if instrument.environment_id == "puzzle_hints":
        stimulus = PuzzlePublicStimulus.model_validate(instrument.public_stimulus)
        private_data = PuzzlePrivateData.model_validate(instrument.private_data)
        validate_puzzle_stimulus(stimulus, private_data)

        expected_action_ids = {"continue", "hint", "next_step", "solution"}
        if set(action_ids) != expected_action_ids:
            raise ValueError(
                f"Puzzle action_specs must exactly contain {expected_action_ids}, got {set(action_ids)}"
            )

    elif instrument.environment_id == "bret_discrete":
        stimulus = BretPublicStimulus.model_validate(instrument.public_stimulus)
        if len(stimulus.options) != 4:
            raise ValueError(f"BRET must have exactly 4 options, got {len(stimulus.options)}")

        option_action_ids = [opt.action_id for opt in stimulus.options]
        if set(option_action_ids) != set(action_ids):
            raise ValueError(
                f"BRET stimulus options ({option_action_ids}) do not match action_specs ({action_ids})"
            )

        k_values = []
        for opt in stimulus.options:
            validate_bret_params(stimulus.num_boxes, stimulus.reward_per_box, opt.k)
            k_values.append(opt.k)

        if 0 not in k_values:
            raise ValueError("BRET options must include a k=0 (collect 0) option")

        is_tutorial = instrument.private_data.get("is_tutorial", False)
        if is_tutorial:
            tut_type = instrument.private_data.get("tutorial_type")
            if tut_type not in ("demonstration", "comprehension"):
                raise ValueError(
                    f"BRET tutorial must specify tutorial_type as 'demonstration' or 'comprehension', got {tut_type}"
                )
            if tut_type == "demonstration":
                demos = instrument.private_data.get("fixed_demonstrations")
                if not demos or not isinstance(demos, list):
                    raise ValueError("Demonstration tutorial must include fixed_demonstrations list")
            elif tut_type == "comprehension":
                comp = instrument.private_data.get("comprehension_check")
                if not comp or not isinstance(comp, dict) or "questions" not in comp:
                    raise ValueError("Comprehension tutorial must include comprehension_check questions")

    else:
        raise ValueError(f"Unknown environment_id: {instrument.environment_id}")

    if instrument.author_status == "drafted":
        instrument.author_status = "engine_validated"

    return instrument


def load_and_validate_instrument(path: Path | str) -> Instrument:
    """Load JSON from path, parse into Instrument, and strictly validate."""
    p = Path(path)
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    instrument = Instrument.model_validate(data)
    return validate_instrument(instrument)
