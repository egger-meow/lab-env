"""Tests for SQLite storage layer, idempotency, and session ZIP export."""

import io
import json
import zipfile
import pytest
from preference_lab.domain.schemas import DecisionRecord, Instrument, Session, Trial, TrialPrivate
from preference_lab.storage.sqlite import Storage


def test_storage_session_and_trial_lifecycle():
    storage = Storage(":memory:")

    # 1. Create Session
    session = Session(
        session_id="s1",
        participant_id="p1",
        session_code="PL-TEST",
        mode="pilot",
        protocol_id="pilot_v001",
        protocol_version="0.1.0",
        environment_order=["puzzle_hints"],
        created_at="2026-10-11T12:00:00Z",
    )
    storage.create_session(session)
    fetched_s = storage.get_session("s1")
    assert fetched_s is not None
    assert fetched_s.session_code == "PL-TEST"

    # 2. Create Trial & Private data
    trial = Trial(
        trial_id="t1",
        session_id="s1",
        participant_id="p1",
        environment_id="puzzle_hints",
        item_id="pz_practice_01",
        instrument_hash="h" * 64,
        protocol_hash="p" * 64,
        collection_index=0,
        status="active",
        state_version=1,
        public_state={"board": [None, None, None, None]},
        created_at="2026-10-11T12:00:00Z",
    )
    trial_private = TrialPrivate(
        trial_id="t1",
        bomb_index=None,
        random_seed=42,
        internal_state={"expected_solution": ["moon", "key", "star", "leaf"]},
    )
    storage.create_trial(trial, trial_private)

    fetched_t = storage.get_trial("t1")
    assert fetched_t is not None
    assert fetched_t.status == "active"

    fetched_tp = storage.get_trial_private("t1")
    assert fetched_tp is not None
    assert fetched_tp.random_seed == 42


def test_storage_event_sequence_monotonic():
    storage = Storage(":memory:")
    storage.create_session(
        Session(
            session_id="s1",
            participant_id="p1",
            session_code="PL-SEQ",
            mode="pilot",
            protocol_id="pilot_v001",
            protocol_version="0.1.0",
            environment_order=["puzzle_hints"],
            created_at="2026-10-11T12:00:00Z",
        )
    )
    storage.create_trial(
        Trial(
            trial_id="t1",
            session_id="s1",
            participant_id="p1",
            environment_id="puzzle_hints",
            item_id="pz_practice_01",
            instrument_hash="h" * 64,
            protocol_hash="p" * 64,
            collection_index=0,
            status="active",
            state_version=1,
            public_state={},
            created_at="2026-10-11T12:00:00Z",
        ),
        TrialPrivate(trial_id="t1", internal_state={}),
    )

    evt1 = storage.add_event("s1", "t1", "e1", {}, 1, 2)
    evt2 = storage.add_event("s1", "t1", "e2", {}, 2, 3)
    evt3 = storage.add_event("s1", "t1", "e3", {}, 3, 4)

    assert evt1.sequence_no == 1
    assert evt2.sequence_no == 2
    assert evt3.sequence_no == 3

    all_evts = storage.get_events_for_session("s1")
    assert [e.sequence_no for e in all_evts] == [1, 2, 3]


def test_decision_idempotency():
    storage = Storage(":memory:")
    storage.create_session(
        Session(
            session_id="s1",
            participant_id="p1",
            session_code="PL-IDEMP",
            mode="pilot",
            protocol_id="pilot_v001",
            protocol_version="0.1.0",
            environment_order=["puzzle_hints"],
            created_at="2026-10-11T12:00:00Z",
        )
    )
    storage.create_trial(
        Trial(
            trial_id="t1",
            session_id="s1",
            participant_id="p1",
            environment_id="puzzle_hints",
            item_id="pz_practice_01",
            instrument_hash="h" * 64,
            protocol_hash="p" * 64,
            collection_index=0,
            status="active",
            state_version=1,
            public_state={},
            created_at="2026-10-11T12:00:00Z",
        ),
        TrialPrivate(trial_id="t1", internal_state={}),
    )

    valid_actions = {"continue", "hint", "next_step", "solution"}
    record = DecisionRecord(
        decision_id="d1",
        trial_id="t1",
        public_observation_snapshot={},
        observation_hash="h" * 64,
        acceptable_by_action={"continue": "yes", "hint": "yes", "next_step": "yes", "solution": "yes"},
        selected_action_id="hint",
        answered_at="2026-10-11T12:00:00Z",
        deliberation_ms=1000,
    )

    r1, is_new1 = storage.commit_decision(record, "idemp_key_123", valid_actions)
    assert is_new1 is True

    # Same idempotency key re-sent: must return existing record and is_new = False
    r2, is_new2 = storage.commit_decision(record, "idemp_key_123", valid_actions)
    assert is_new2 is False
    assert r2.decision_id == r1.decision_id


def test_export_session_zip_contents():
    storage = Storage(":memory:")
    storage.create_session(
        Session(
            session_id="s1",
            participant_id="p1",
            session_code="PL-ZIP",
            mode="pilot",
            protocol_id="pilot_v001",
            protocol_version="0.1.0",
            environment_order=["puzzle_hints"],
            created_at="2026-10-11T12:00:00Z",
        )
    )
    storage.create_trial(
        Trial(
            trial_id="t1",
            session_id="s1",
            participant_id="p1",
            environment_id="puzzle_hints",
            item_id="pz_practice_01",
            instrument_hash="h" * 64,
            protocol_hash="p" * 64,
            collection_index=0,
            status="active",
            state_version=1,
            public_state={},
            created_at="2026-10-11T12:00:00Z",
        ),
        TrialPrivate(trial_id="t1", internal_state={}),
    )
    storage.add_event("s1", "t1", "trial_started", {}, 1, 1)

    zip_bytes = storage.export_session_zip("s1")
    assert isinstance(zip_bytes, bytes)
    assert len(zip_bytes) > 0

    # Unpack and verify all required files per Spec Section 10.4
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        namelist = zf.namelist()
        expected_files = [
            "manifest.json",
            "instruments.json",
            "decisions.json",
            "events.jsonl",
            "outcomes.json",
            "private_replay.json",
        ]
        for ef in expected_files:
            assert ef in namelist, f"Missing file in export ZIP: {ef}"

        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        assert manifest["session_id"] == "s1"
        assert manifest["trial_count"] == 1
        assert manifest["event_count"] == 1
