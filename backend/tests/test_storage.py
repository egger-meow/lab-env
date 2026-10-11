"""Tests for SQLite storage layer, atomic decision execution, idempotency, and session ZIP export."""

import io
import json
import zipfile
import pytest
from preference_lab.domain.canonical import sha256_canonical_json
from preference_lab.domain.schemas import DecisionRecord, Instrument, Outcome, Session, Trial, TrialPrivate
from preference_lab.storage.sqlite import Storage


def test_storage_session_and_trial_lifecycle():
    storage = Storage(":memory:")

    # 1. Create Session
    session = Session(
        session_id="s1",
        participant_id="p1",
        session_code="PL-TEST",
        session_token="tok_test_123",
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
    assert fetched_s.session_token == "tok_test_123"

    # Fetch by token
    fetched_by_tok = storage.get_session_by_token("tok_test_123")
    assert fetched_by_tok is not None
    assert fetched_by_tok.session_id == "s1"

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
            session_token="tok_seq",
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


def test_decision_idempotency_and_hash_collision():
    storage = Storage(":memory:")
    storage.create_session(
        Session(
            session_id="s1",
            participant_id="p1",
            session_code="PL-IDEMP",
            session_token="tok_idemp",
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

    # Same key with different payload: must raise ValueError
    record_diff = DecisionRecord(
        decision_id="d2",
        trial_id="t1",
        public_observation_snapshot={},
        observation_hash="h" * 64,
        acceptable_by_action={"continue": "yes", "hint": "yes", "next_step": "yes", "solution": "yes"},
        selected_action_id="continue",
        answered_at="2026-10-11T12:00:00Z",
        deliberation_ms=1000,
    )
    with pytest.raises(ValueError, match="Idempotency key collision"):
        storage.commit_decision(record_diff, "idemp_key_123", valid_actions)


def test_commit_decision_atomic():
    storage = Storage(":memory:")
    storage.create_session(
        Session(
            session_id="s1",
            participant_id="p1",
            session_code="PL-ATOMIC",
            session_token="tok_atomic",
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
            status="decision_open",
            state_version=2,
            public_state={"board": [None, None, None, None]},
            created_at="2026-10-11T12:00:00Z",
        ),
        TrialPrivate(trial_id="t1", internal_state={}),
    )

    valid_actions = {"continue", "hint", "next_step", "solution"}
    record = DecisionRecord(
        decision_id="dec_01",
        trial_id="t1",
        public_observation_snapshot={"env": "puzzle"},
        observation_hash="h" * 64,
        acceptable_by_action={"continue": "yes", "hint": "yes", "next_step": "yes", "solution": "yes"},
        selected_action_id="hint",
        answered_at="2026-10-11T12:00:00Z",
        deliberation_ms=2500,
    )
    outcome = Outcome(
        outcome_id="out_01",
        trial_id="t1",
        action_id="hint",
        executed_payload={"hint": "text"},
        result_summary={"hint": "text"},
        completed_at="2026-10-11T12:00:00Z",
    )

    rec, is_new, new_ver, out = storage.commit_decision_atomic(
        record=record,
        idempotency_key="key_atomic_1",
        valid_action_ids=valid_actions,
        expected_state_version=2,
        new_public_state={"board": [None, None, None, None], "revealed_hint": "text"},
        new_status="active",
        outcome=outcome,
        event_payload={"decision_id": "dec_01"},
    )
    assert is_new is True
    assert new_ver == 3

    # Trial status must be updated
    trial = storage.get_trial("t1")
    assert trial.status == "active"
    assert trial.state_version == 3

    # Outcome must be recorded
    saved_outcome = storage.get_outcome("t1")
    assert saved_outcome is not None
    assert saved_outcome.action_id == "hint"

    # Events must contain decision_committed
    events = storage.get_events_for_session("s1")
    assert any(e.event_type == "decision_committed" for e in events)


def test_instrument_hash_immutability():
    storage = Storage(":memory:")

    # Save instrument v1
    inst1 = Instrument(
        schema_version="v001",
        instrument_id="pz_v001",
        instrument_version="0.1.0",
        environment_id="puzzle_hints",
        item_id="pz_01",
        template_id="tpl_01",
        language="zh-TW",
        public_stimulus={"num_positions": 4, "items": ["a", "b", "c", "d"], "clues": []},
        action_specs=[],
        author_status="engine_validated",
        private_data={"v": 1},
    )
    hash1 = storage.save_instrument(inst1)

    # Save instrument v2 with same item_id but different private_data
    inst2 = Instrument(
        schema_version="v001",
        instrument_id="pz_v001",
        instrument_version="0.2.0",
        environment_id="puzzle_hints",
        item_id="pz_01",
        template_id="tpl_01",
        language="zh-TW",
        public_stimulus={"num_positions": 4, "items": ["a", "b", "c", "d"], "clues": []},
        action_specs=[],
        author_status="engine_validated",
        private_data={"v": 2},
    )
    hash2 = storage.save_instrument(inst2)

    assert hash1 != hash2

    # Fetching by original hash1 must strictly return v1!
    fetched_v1 = storage.get_instrument_by_hash(hash1)
    assert fetched_v1 is not None
    assert fetched_v1.private_data["v"] == 1

    fetched_v2 = storage.get_instrument_by_hash(hash2)
    assert fetched_v2 is not None
    assert fetched_v2.private_data["v"] == 2


def test_export_session_zip_contents():
    storage = Storage(":memory:")
    storage.create_session(
        Session(
            session_id="s1",
            participant_id="p1",
            session_code="PL-ZIP",
            session_token="tok_zip",
            mode="pilot",
            protocol_id="pilot_v001",
            protocol_version="0.1.0",
            environment_order=["puzzle_hints"],
            created_at="2026-10-11T12:00:00Z",
        )
    )
    # Save instrument to cache
    inst = Instrument(
        schema_version="v001",
        instrument_id="pz_v001",
        instrument_version="0.1.0",
        environment_id="puzzle_hints",
        item_id="pz_practice_01",
        template_id="tpl_01",
        language="zh-TW",
        public_stimulus={"num_positions": 4, "items": ["a", "b", "c", "d"], "clues": []},
        action_specs=[],
        author_status="engine_validated",
        private_data={},
    )
    inst_hash = storage.save_instrument(inst)

    storage.create_trial(
        Trial(
            trial_id="t1",
            session_id="s1",
            participant_id="p1",
            environment_id="puzzle_hints",
            item_id="pz_practice_01",
            instrument_hash=inst_hash,
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

        inst_json = json.loads(zf.read("instruments.json").decode("utf-8"))
        assert inst_hash in inst_json


def test_atomic_rollback_on_simulated_failure(monkeypatch):
    """Verify that any mid-transaction failure rolls back ALL changes cleanly, leaving zero partial state."""
    storage = Storage(":memory:")
    storage.create_session(
        Session(
            session_id="s1",
            participant_id="p1",
            session_code="PL-ROLLBACK",
            session_token="tok_rollback",
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
            status="decision_open",
            state_version=2,
            public_state={"board": [None, None, None, None]},
            created_at="2026-10-11T12:00:00Z",
        ),
        TrialPrivate(trial_id="t1", internal_state={}),
    )

    valid_actions = {"continue", "hint", "next_step", "solution"}
    record = DecisionRecord(
        decision_id="dec_rb",
        trial_id="t1",
        public_observation_snapshot={"env": "puzzle"},
        observation_hash="h" * 64,
        acceptable_by_action={"continue": "yes", "hint": "yes", "next_step": "yes", "solution": "yes"},
        selected_action_id="hint",
        answered_at="2026-10-11T12:00:00Z",
        deliberation_ms=2500,
    )
    outcome = Outcome(
        outcome_id="out_rb",
        trial_id="t1",
        action_id="hint",
        executed_payload={"hint": "text"},
        result_summary={"hint": "text"},
        completed_at="2026-10-11T12:00:00Z",
    )

    # Pass an event_payload with an un-serializable object to fail in step 6 after decision & trial & outcome inserts
    with pytest.raises(TypeError):
        storage.commit_decision_atomic(
            record=record,
            idempotency_key="key_rb_1",
            valid_action_ids=valid_actions,
            expected_state_version=2,
            new_public_state={"board": [None, None, None, None], "revealed_hint": "text"},
            new_status="active",
            outcome=outcome,
            event_payload={"unserializable": object()},
        )

    # Rollback verification:
    # 1. Decision must NOT exist (rolled back!)
    assert storage.get_decision("t1") is None
    # 2. Trial status must still be 'decision_open' with state_version = 2 (rolled back!)
    trial = storage.get_trial("t1")
    assert trial.status == "decision_open"
    assert trial.state_version == 2
    # 3. Outcome must NOT exist (rolled back!)
    assert storage.get_outcome("t1") is None
    # 4. No event recorded
    evts = storage.get_events_for_session("s1")
    assert len(evts) == 0


def test_unique_decision_index_constraint():
    """Verify DB-level constraint UNIQUE(trial_id, decision_index)."""
    storage = Storage(":memory:")
    storage.create_session(
        Session(
            session_id="s1",
            participant_id="p1",
            session_code="PL-UNIQ",
            session_token="tok_uniq",
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
            status="decision_open",
            state_version=2,
            public_state={},
            created_at="2026-10-11T12:00:00Z",
        ),
        TrialPrivate(trial_id="t1", internal_state={}),
    )

    valid_actions = {"continue", "hint", "next_step", "solution"}
    rec1 = DecisionRecord(
        decision_id="d1",
        trial_id="t1",
        decision_index=1,
        public_observation_snapshot={},
        observation_hash="h" * 64,
        acceptable_by_action={"continue": "yes", "hint": "yes", "next_step": "yes", "solution": "yes"},
        selected_action_id="hint",
        answered_at="2026-10-11T12:00:00Z",
        deliberation_ms=1000,
    )
    storage.commit_decision(rec1, "key_u_1", valid_actions)

    rec2 = DecisionRecord(
        decision_id="d2",
        trial_id="t1",
        decision_index=1,
        public_observation_snapshot={},
        observation_hash="h" * 64,
        acceptable_by_action={"continue": "yes", "hint": "yes", "next_step": "yes", "solution": "yes"},
        selected_action_id="continue",
        answered_at="2026-10-11T12:00:00Z",
        deliberation_ms=1000,
    )
    # Different idempotency key but same (trial_id, decision_index) -> SQLite IntegrityError
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        storage.commit_decision(rec2, "key_u_2", valid_actions)

