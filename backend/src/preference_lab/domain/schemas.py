"""Domain data schemas according to PREFERENCE_LAB_SPEC.md."""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


class ActionSpec(BaseModel):
    action_id: str
    label: str
    description: str
    params: dict[str, Any] = Field(default_factory=dict)


class Instrument(BaseModel):
    schema_version: str = "v001"
    instrument_id: str
    instrument_version: str
    environment_id: Literal["puzzle_hints", "bret_discrete"]
    item_id: str
    template_id: str
    language: str = "zh-TW"
    public_stimulus: dict[str, Any]
    action_specs: list[ActionSpec]
    author_status: Literal["drafted", "engine_validated", "human_reviewed"] = "engine_validated"
    private_data: dict[str, Any] = Field(default_factory=dict)


class Trial(BaseModel):
    trial_id: str
    session_id: str
    participant_id: str
    environment_id: Literal["puzzle_hints", "bret_discrete"]
    item_id: str
    instrument_hash: str
    protocol_hash: str
    collection_index: int
    status: Literal[
        "created",
        "active",
        "decision_open",
        "decision_committed",
        "executing",
        "completed",
        "completed_without_decision",
        "skipped",
        "aborted",
    ]
    state_version: int = 1
    public_state: dict[str, Any]
    active_play_ms: int = 0
    display_order: list[str] = Field(default_factory=list)
    created_at: str


class TrialPrivate(BaseModel):
    trial_id: str
    bomb_index: int | None = None
    random_seed: int | None = None
    internal_state: dict[str, Any] = Field(default_factory=dict)


class DecisionRecord(BaseModel):
    decision_id: str
    trial_id: str
    decision_index: int = 1
    public_observation_snapshot: dict[str, Any]
    observation_hash: str
    acceptable_by_action: dict[str, Literal["yes", "no", "unsure"]]
    selected_action_id: str
    preferred_action_ids: list[str] | None = None
    reason: str | None = None
    selection_acceptability_override: bool = False
    answered_at: str
    deliberation_ms: int
    source: Literal["human_gui", "human_import", "synthetic_mock"] = "human_gui"


class Event(BaseModel):
    event_id: str
    session_id: str
    trial_id: str
    sequence_no: int
    timestamp_utc: str
    event_type: str
    payload: dict[str, Any]
    state_version_before: int
    state_version_after: int


class Outcome(BaseModel):
    outcome_id: str
    trial_id: str
    action_id: str
    executed_payload: dict[str, Any]
    result_summary: dict[str, Any]
    completed_at: str


class Session(BaseModel):
    session_id: str
    participant_id: str
    session_code: str
    mode: Literal["practice", "pilot", "formal"] = "pilot"
    protocol_id: str
    protocol_version: str
    environment_order: list[str]
    status: Literal["created", "active", "completed", "aborted"] = "created"
    created_at: str
    completed_at: str | None = None
