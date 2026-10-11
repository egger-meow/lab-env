"""Tests for DecisionRecord validation rules according to PREFERENCE_LAB_SPEC.md."""

import pytest
from preference_lab.domain.schemas import DecisionRecord
from preference_lab.domain.validation import validate_decision_record


def make_sample_record(
    acceptable_by_action: dict | None = None,
    selected_action_id: str = "continue",
    preferred_action_ids: list[str] | None = None,
    selection_acceptability_override: bool = False,
    deliberation_ms: int = 2500,
) -> DecisionRecord:
    if acceptable_by_action is None:
        acceptable_by_action = {
            "continue": "yes",
            "hint": "yes",
            "next_step": "no",
            "solution": "no",
        }
    return DecisionRecord(
        decision_id="dec_001",
        trial_id="tr_001",
        public_observation_snapshot={"board": ["moon", None, None, None]},
        observation_hash="dummy_hash_64chars" + "0" * 46,
        acceptable_by_action=acceptable_by_action,
        selected_action_id=selected_action_id,
        preferred_action_ids=preferred_action_ids,
        selection_acceptability_override=selection_acceptability_override,
        answered_at="2026-10-11T12:00:00Z",
        deliberation_ms=deliberation_ms,
    )


VALID_ACTIONS = {"continue", "hint", "next_step", "solution"}


def test_valid_decision_passes():
    record = make_sample_record()
    validate_decision_record(record, VALID_ACTIONS)


def test_empty_acceptability_dict_rejected():
    record = make_sample_record(acceptable_by_action={})
    with pytest.raises(ValueError, match="acceptable_by_action must cover all valid actions"):
        validate_decision_record(record, VALID_ACTIONS)


def test_missing_action_in_acceptability_rejected():
    record = make_sample_record(
        acceptable_by_action={"continue": "yes", "hint": "yes", "next_step": "no"}
    )
    with pytest.raises(ValueError, match="acceptable_by_action must cover all valid actions"):
        validate_decision_record(record, VALID_ACTIONS)


def test_invalid_selected_action_rejected():
    record = make_sample_record(selected_action_id="non_existent_action")
    with pytest.raises(ValueError, match="selected_action_id 'non_existent_action' is not in valid actions"):
        validate_decision_record(record, VALID_ACTIONS)


def test_preferred_action_ids_must_include_selected():
    # preferred does not contain selected ('continue')
    record = make_sample_record(
        selected_action_id="continue",
        preferred_action_ids=["hint"],
    )
    with pytest.raises(ValueError, match="preferred_action_ids must include selected_action_id"):
        validate_decision_record(record, VALID_ACTIONS)


def test_preferred_action_ids_with_invalid_action_rejected():
    record = make_sample_record(
        selected_action_id="continue",
        preferred_action_ids=["continue", "fake_action"],
    )
    with pytest.raises(ValueError, match="preferred_action_ids contains invalid actions"):
        validate_decision_record(record, VALID_ACTIONS)


def test_selecting_unacceptable_requires_override():
    # 'solution' is rated 'no'
    record = make_sample_record(
        selected_action_id="solution",
        selection_acceptability_override=False,
    )
    with pytest.raises(ValueError, match="selection_acceptability_override must be True"):
        validate_decision_record(record, VALID_ACTIONS)

    # When override is True, it is accepted!
    record_with_override = make_sample_record(
        selected_action_id="solution",
        selection_acceptability_override=True,
    )
    validate_decision_record(record_with_override, VALID_ACTIONS)


def test_negative_deliberation_ms_rejected():
    record = make_sample_record(deliberation_ms=-100)
    with pytest.raises(ValueError, match="deliberation_ms cannot be negative"):
        validate_decision_record(record, VALID_ACTIONS)
