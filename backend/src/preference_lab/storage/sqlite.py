"""SQLite transaction, atomic decision execution, and event storage according to PREFERENCE_LAB_SPEC.md."""

from __future__ import annotations

import io
import json
import sqlite3
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from preference_lab.domain.canonical import (
    canonical_json_str,
    sha256_canonical_json,
)
from preference_lab.domain.schemas import (
    DecisionRecord,
    Event,
    Instrument,
    Outcome,
    Session,
    Trial,
    TrialPrivate,
)
from preference_lab.domain.validation import validate_decision_record


def get_utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Storage:
    def __init__(self, db_path: Path | str = ":memory:"):
        self.db_path = str(db_path)
        self._is_memory = self.db_path == ":memory:"
        self._mem_conn: sqlite3.Connection | None = None
        if self._is_memory:
            self._mem_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._mem_conn.row_factory = sqlite3.Row
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        if self._is_memory and self._mem_conn is not None:
            return self._mem_conn
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def _init_db(self) -> None:
        conn = self._get_connection()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                participant_id TEXT NOT NULL,
                session_code TEXT UNIQUE NOT NULL,
                session_token TEXT UNIQUE NOT NULL,
                mode TEXT NOT NULL,
                protocol_id TEXT NOT NULL,
                protocol_version TEXT NOT NULL,
                environment_order TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                completed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS instruments_cache (
                canonical_hash TEXT PRIMARY KEY,
                item_id TEXT NOT NULL,
                instrument_id TEXT NOT NULL,
                instrument_version TEXT NOT NULL,
                environment_id TEXT NOT NULL,
                template_id TEXT NOT NULL,
                data_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS trials (
                trial_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL REFERENCES sessions(session_id),
                participant_id TEXT NOT NULL,
                environment_id TEXT NOT NULL,
                item_id TEXT NOT NULL,
                instrument_hash TEXT NOT NULL REFERENCES instruments_cache(canonical_hash),
                protocol_hash TEXT NOT NULL,
                collection_index INTEGER NOT NULL,
                status TEXT NOT NULL,
                state_version INTEGER NOT NULL DEFAULT 1,
                public_state TEXT NOT NULL,
                active_play_ms INTEGER NOT NULL DEFAULT 0,
                display_order TEXT NOT NULL,
                created_at TEXT NOT NULL,
                completed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS trials_private (
                trial_id TEXT PRIMARY KEY REFERENCES trials(trial_id),
                bomb_index INTEGER,
                random_seed INTEGER,
                internal_state TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS decisions (
                decision_id TEXT PRIMARY KEY,
                trial_id TEXT NOT NULL REFERENCES trials(trial_id),
                decision_index INTEGER NOT NULL DEFAULT 1,
                public_observation_snapshot TEXT NOT NULL,
                observation_hash TEXT NOT NULL,
                acceptable_by_action TEXT NOT NULL,
                selected_action_id TEXT NOT NULL,
                preferred_action_ids TEXT,
                reason TEXT,
                selection_acceptability_override INTEGER NOT NULL DEFAULT 0,
                answered_at TEXT NOT NULL,
                deliberation_ms INTEGER NOT NULL,
                source TEXT NOT NULL,
                idempotency_key TEXT UNIQUE NOT NULL,
                request_payload_hash TEXT NOT NULL,
                UNIQUE(trial_id, decision_index)
            );

            CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL REFERENCES sessions(session_id),
                trial_id TEXT NOT NULL REFERENCES trials(trial_id),
                sequence_no INTEGER NOT NULL,
                timestamp_utc TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload TEXT NOT NULL,
                state_version_before INTEGER NOT NULL,
                state_version_after INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS outcomes (
                outcome_id TEXT PRIMARY KEY,
                trial_id TEXT NOT NULL REFERENCES trials(trial_id),
                action_id TEXT NOT NULL,
                executed_payload TEXT NOT NULL,
                result_summary TEXT NOT NULL,
                completed_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_events_session_seq ON events(session_id, sequence_no);
            CREATE INDEX IF NOT EXISTS idx_trials_session ON trials(session_id, collection_index);
            CREATE INDEX IF NOT EXISTS idx_inst_item_id ON instruments_cache(item_id);
        """)

    def save_instrument(self, instrument: Instrument) -> str:
        """Cache an instrument by its immutable canonical SHA-256 hash."""
        data_dict = instrument.model_dump()
        canonical_hash = sha256_canonical_json(data_dict)
        data_json = canonical_json_str(data_dict)

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO instruments_cache (canonical_hash, item_id, instrument_id, instrument_version, environment_id, template_id, data_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(canonical_hash) DO UPDATE SET
                    data_json=excluded.data_json;
                """,
                (
                    canonical_hash,
                    instrument.item_id,
                    instrument.instrument_id,
                    instrument.instrument_version,
                    instrument.environment_id,
                    instrument.template_id,
                    data_json,
                ),
            )
        return canonical_hash

    def get_instrument_by_hash(self, canonical_hash: str) -> Instrument | None:
        """Fetch instrument strictly by its immutable canonical hash."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT data_json FROM instruments_cache WHERE canonical_hash = ?",
                (canonical_hash,),
            ).fetchone()
            if not row:
                return None
            return Instrument.model_validate(json.loads(row["data_json"]))

    def get_instrument(self, item_id: str) -> Instrument | None:
        """Fetch latest instrument for item_id."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT data_json FROM instruments_cache WHERE item_id = ? ORDER BY rowid DESC LIMIT 1",
                (item_id,),
            ).fetchone()
            if not row:
                return None
            return Instrument.model_validate(json.loads(row["data_json"]))

    def create_session(self, session: Session) -> Session:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO sessions (session_id, participant_id, session_code, session_token, mode, protocol_id, protocol_version, environment_order, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session.session_id,
                    session.participant_id,
                    session.session_code,
                    session.session_token,
                    session.mode,
                    session.protocol_id,
                    session.protocol_version,
                    json.dumps(session.environment_order),
                    session.status,
                    session.created_at,
                ),
            )
        return session

    def get_session(self, session_id: str) -> Session | None:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            if not row:
                return None
            return Session(
                session_id=row["session_id"],
                participant_id=row["participant_id"],
                session_code=row["session_code"],
                session_token=row["session_token"],
                mode=row["mode"],
                protocol_id=row["protocol_id"],
                protocol_version=row["protocol_version"],
                environment_order=json.loads(row["environment_order"]),
                status=row["status"],
                created_at=row["created_at"],
                completed_at=row["completed_at"],
            )

    def get_session_by_code(self, session_code: str) -> Session | None:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE session_code = ?", (session_code,)
            ).fetchone()
            if not row:
                return None
            return Session(
                session_id=row["session_id"],
                participant_id=row["participant_id"],
                session_code=row["session_code"],
                session_token=row["session_token"],
                mode=row["mode"],
                protocol_id=row["protocol_id"],
                protocol_version=row["protocol_version"],
                environment_order=json.loads(row["environment_order"]),
                status=row["status"],
                created_at=row["created_at"],
                completed_at=row["completed_at"],
            )

    def get_session_by_token(self, session_token: str) -> Session | None:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE session_token = ?", (session_token,)
            ).fetchone()
            if not row:
                return None
            return Session(
                session_id=row["session_id"],
                participant_id=row["participant_id"],
                session_code=row["session_code"],
                session_token=row["session_token"],
                mode=row["mode"],
                protocol_id=row["protocol_id"],
                protocol_version=row["protocol_version"],
                environment_order=json.loads(row["environment_order"]),
                status=row["status"],
                created_at=row["created_at"],
                completed_at=row["completed_at"],
            )

    def list_sessions(self) -> list[Session]:
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM sessions ORDER BY created_at DESC").fetchall()
            return [
                Session(
                    session_id=row["session_id"],
                    participant_id=row["participant_id"],
                    session_code=row["session_code"],
                    session_token=row["session_token"],
                    mode=row["mode"],
                    protocol_id=row["protocol_id"],
                    protocol_version=row["protocol_version"],
                    environment_order=json.loads(row["environment_order"]),
                    status=row["status"],
                    created_at=row["created_at"],
                    completed_at=row["completed_at"],
                )
                for row in rows
            ]

    def create_trial(self, trial: Trial, trial_private: TrialPrivate) -> Trial:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO trials (trial_id, session_id, participant_id, environment_id, item_id, instrument_hash, protocol_hash, collection_index, status, state_version, public_state, active_play_ms, display_order, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trial.trial_id,
                    trial.session_id,
                    trial.participant_id,
                    trial.environment_id,
                    trial.item_id,
                    trial.instrument_hash,
                    trial.protocol_hash,
                    trial.collection_index,
                    trial.status,
                    trial.state_version,
                    json.dumps(trial.public_state),
                    trial.active_play_ms,
                    json.dumps(trial.display_order),
                    trial.created_at,
                ),
            )
            conn.execute(
                """
                INSERT INTO trials_private (trial_id, bomb_index, random_seed, internal_state)
                VALUES (?, ?, ?, ?)
                """,
                (
                    trial_private.trial_id,
                    trial_private.bomb_index,
                    trial_private.random_seed,
                    json.dumps(trial_private.internal_state),
                ),
            )
        return trial

    def get_trial(self, trial_id: str) -> Trial | None:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM trials WHERE trial_id = ?", (trial_id,)).fetchone()
            if not row:
                return None
            return Trial(
                trial_id=row["trial_id"],
                session_id=row["session_id"],
                participant_id=row["participant_id"],
                environment_id=row["environment_id"],
                item_id=row["item_id"],
                instrument_hash=row["instrument_hash"],
                protocol_hash=row["protocol_hash"],
                collection_index=row["collection_index"],
                status=row["status"],
                state_version=row["state_version"],
                public_state=json.loads(row["public_state"]),
                active_play_ms=row["active_play_ms"],
                display_order=json.loads(row["display_order"]),
                created_at=row["created_at"],
            )

    def get_trial_private(self, trial_id: str) -> TrialPrivate | None:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM trials_private WHERE trial_id = ?", (trial_id,)
            ).fetchone()
            if not row:
                return None
            return TrialPrivate(
                trial_id=row["trial_id"],
                bomb_index=row["bomb_index"],
                random_seed=row["random_seed"],
                internal_state=json.loads(row["internal_state"]),
            )

    def get_trials_for_session(self, session_id: str) -> list[Trial]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM trials WHERE session_id = ? ORDER BY collection_index ASC",
                (session_id,),
            ).fetchall()
            return [
                Trial(
                    trial_id=row["trial_id"],
                    session_id=row["session_id"],
                    participant_id=row["participant_id"],
                    environment_id=row["environment_id"],
                    item_id=row["item_id"],
                    instrument_hash=row["instrument_hash"],
                    protocol_hash=row["protocol_hash"],
                    collection_index=row["collection_index"],
                    status=row["status"],
                    state_version=row["state_version"],
                    public_state=json.loads(row["public_state"]),
                    active_play_ms=row["active_play_ms"],
                    display_order=json.loads(row["display_order"]),
                    created_at=row["created_at"],
                )
                for row in rows
            ]

    def update_trial_state(
        self,
        trial_id: str,
        public_state: dict[str, Any],
        status: str,
        active_play_ms: int,
        expected_state_version: int,
    ) -> int:
        """Atomically update trial state and bump state_version."""
        new_version = expected_state_version + 1
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                UPDATE trials
                SET public_state = ?, status = ?, active_play_ms = ?, state_version = ?
                WHERE trial_id = ? AND state_version = ?
                """,
                (
                    json.dumps(public_state),
                    status,
                    active_play_ms,
                    new_version,
                    trial_id,
                    expected_state_version,
                ),
            )
            if cursor.rowcount == 0:
                raise ValueError(
                    f"State version conflict for trial {trial_id}: expected {expected_state_version}"
                )
        return new_version

    def update_trial_state_atomic(
        self,
        trial_id: str,
        public_state: dict[str, Any],
        status: str,
        active_play_ms: int,
        expected_state_version: int,
        events: list[tuple[str, dict[str, Any]]],
    ) -> int:
        """Atomically update trial state, bump version, and record all events in one SQLite transaction."""
        new_version = expected_state_version + 1
        timestamp = get_utc_now_iso()

        with self._get_connection() as conn:
            row_trial = conn.execute(
                "SELECT session_id, status FROM trials WHERE trial_id = ?", (trial_id,)
            ).fetchone()
            if not row_trial:
                raise ValueError(f"Trial {trial_id} not found")
            prev_status = row_trial["status"]
            session_id = row_trial["session_id"]

            cursor = conn.execute(
                """
                UPDATE trials
                SET public_state = ?, status = ?, active_play_ms = ?, state_version = ?
                WHERE trial_id = ? AND state_version = ?
                """,
                (
                    json.dumps(public_state),
                    status,
                    active_play_ms,
                    new_version,
                    trial_id,
                    expected_state_version,
                ),
            )
            if cursor.rowcount == 0:
                raise ValueError(
                    f"State version conflict for trial {trial_id}: expected {expected_state_version}"
                )

            row_seq = conn.execute(
                "SELECT COALESCE(MAX(sequence_no), 0) + 1 AS next_seq FROM events WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            seq_no = row_seq["next_seq"]

            all_events = list(events)
            terminal_statuses = ("completed", "completed_without_decision", "skipped", "aborted")
            if prev_status not in terminal_statuses and status in terminal_statuses and not any(ev[0] == "trial_ended" for ev in all_events):
                all_events.append(("trial_ended", {"status": status, "active_play_ms": active_play_ms}))

            for ev_type, ev_payload in all_events:
                ev_id = f"evt_{uuid.uuid4().hex[:12]}"
                conn.execute(
                    """
                    INSERT INTO events (event_id, session_id, trial_id, sequence_no, timestamp_utc, event_type, payload, state_version_before, state_version_after)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ev_id,
                        session_id,
                        trial_id,
                        seq_no,
                        timestamp,
                        ev_type,
                        json.dumps(ev_payload),
                        expected_state_version,
                        new_version,
                    ),
                )
                seq_no += 1

        return new_version

    def add_event(
        self,
        session_id: str,
        trial_id: str,
        event_type: str,
        payload: dict[str, Any],
        state_version_before: int,
        state_version_after: int,
    ) -> Event:
        event_id = f"evt_{uuid.uuid4().hex[:12]}"
        timestamp = get_utc_now_iso()

        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(sequence_no), 0) + 1 AS next_seq FROM events WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            seq_no = row["next_seq"]

            conn.execute(
                """
                INSERT INTO events (event_id, session_id, trial_id, sequence_no, timestamp_utc, event_type, payload, state_version_before, state_version_after)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    session_id,
                    trial_id,
                    seq_no,
                    timestamp,
                    event_type,
                    json.dumps(payload),
                    state_version_before,
                    state_version_after,
                ),
            )

        return Event(
            event_id=event_id,
            session_id=session_id,
            trial_id=trial_id,
            sequence_no=seq_no,
            timestamp_utc=timestamp,
            event_type=event_type,
            payload=payload,
            state_version_before=state_version_before,
            state_version_after=state_version_after,
        )

    def commit_decision(
        self,
        record: DecisionRecord,
        idempotency_key: str,
        valid_action_ids: set[str] | list[str],
    ) -> tuple[DecisionRecord, bool]:
        """Commit a decision record with idempotency and uniqueness checks."""
        validate_decision_record(record, valid_action_ids)
        request_payload_hash = sha256_canonical_json({
            "trial_id": record.trial_id,
            "acceptable_by_action": record.acceptable_by_action,
            "selected_action_id": record.selected_action_id,
            "preferred_action_ids": record.preferred_action_ids,
            "deliberation_ms": record.deliberation_ms,
            "selection_acceptability_override": record.selection_acceptability_override,
            "reason": record.reason,
        })
        with self._get_connection() as conn:
            existing = conn.execute(
                "SELECT * FROM decisions WHERE idempotency_key = ?", (idempotency_key,)
            ).fetchone()
            if existing:
                if existing["request_payload_hash"] != request_payload_hash:
                    raise ValueError("Idempotency key collision with different request payload")
                return DecisionRecord(
                    decision_id=existing["decision_id"],
                    trial_id=existing["trial_id"],
                    decision_index=existing["decision_index"],
                    public_observation_snapshot=json.loads(existing["public_observation_snapshot"]),
                    observation_hash=existing["observation_hash"],
                    acceptable_by_action=json.loads(existing["acceptable_by_action"]),
                    selected_action_id=existing["selected_action_id"],
                    preferred_action_ids=json.loads(existing["preferred_action_ids"]) if existing["preferred_action_ids"] else None,
                    reason=existing["reason"],
                    selection_acceptability_override=bool(existing["selection_acceptability_override"]),
                    answered_at=existing["answered_at"],
                    deliberation_ms=existing["deliberation_ms"],
                    source=existing["source"],
                ), False

            conn.execute(
                """
                INSERT INTO decisions (
                    decision_id, trial_id, decision_index, public_observation_snapshot,
                    observation_hash, acceptable_by_action, selected_action_id,
                    preferred_action_ids, reason, selection_acceptability_override,
                    answered_at, deliberation_ms, source, idempotency_key, request_payload_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.decision_id,
                    record.trial_id,
                    record.decision_index,
                    json.dumps(record.public_observation_snapshot),
                    record.observation_hash,
                    json.dumps(record.acceptable_by_action),
                    record.selected_action_id,
                    json.dumps(record.preferred_action_ids) if record.preferred_action_ids else None,
                    record.reason,
                    1 if record.selection_acceptability_override else 0,
                    record.answered_at,
                    record.deliberation_ms,
                    record.source,
                    idempotency_key,
                    request_payload_hash,
                ),
            )
            return record, True

    def get_decision_by_idempotency_key(
        self, idempotency_key: str
    ) -> tuple[DecisionRecord, str] | None:
        """Fetch decision by idempotency key along with stored request_payload_hash."""
        with self._get_connection() as conn:
            existing = conn.execute(
                "SELECT * FROM decisions WHERE idempotency_key = ?", (idempotency_key,)
            ).fetchone()
            if not existing:
                return None
            return (
                DecisionRecord(
                    decision_id=existing["decision_id"],
                    trial_id=existing["trial_id"],
                    decision_index=existing["decision_index"],
                    public_observation_snapshot=json.loads(
                        existing["public_observation_snapshot"]
                    ),
                    observation_hash=existing["observation_hash"],
                    acceptable_by_action=json.loads(existing["acceptable_by_action"]),
                    selected_action_id=existing["selected_action_id"],
                    preferred_action_ids=(
                        json.loads(existing["preferred_action_ids"])
                        if existing["preferred_action_ids"]
                        else None
                    ),
                    reason=existing["reason"],
                    selection_acceptability_override=bool(
                        existing["selection_acceptability_override"]
                    ),
                    answered_at=existing["answered_at"],
                    deliberation_ms=existing["deliberation_ms"],
                    source=existing["source"],
                ),
                existing["request_payload_hash"],
            )

    def commit_decision_atomic(
        self,
        record: DecisionRecord,
        idempotency_key: str,
        valid_action_ids: set[str] | list[str],
        expected_state_version: int,
        new_public_state: dict[str, Any],
        new_status: str,
        outcome: Outcome,
        event_payload: dict[str, Any],
    ) -> tuple[DecisionRecord, bool, int, Outcome]:
        """Commit decision, update trial status, record outcome, and record event in ONE ATOMIC TRANSACTION.

        Enforces:
        - Must be in 'decision_open' status.
        - UNIQUE(trial_id, decision_index) in database.
        - Idempotency key payload matching.
        - Rollback on any failure.
        """
        validate_decision_record(record, valid_action_ids)
        request_payload_hash = sha256_canonical_json({
            "trial_id": record.trial_id,
            "acceptable_by_action": record.acceptable_by_action,
            "selected_action_id": record.selected_action_id,
            "preferred_action_ids": record.preferred_action_ids,
            "deliberation_ms": record.deliberation_ms,
            "selection_acceptability_override": record.selection_acceptability_override,
            "reason": record.reason,
        })

        with self._get_connection() as conn:
            # 1. Check idempotency
            existing = conn.execute(
                "SELECT * FROM decisions WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()

            if existing:
                if existing["request_payload_hash"] != request_payload_hash:
                    raise ValueError(
                        "Idempotency key collision with different request payload"
                    )
                existing_record = DecisionRecord(
                    decision_id=existing["decision_id"],
                    trial_id=existing["trial_id"],
                    decision_index=existing["decision_index"],
                    public_observation_snapshot=json.loads(
                        existing["public_observation_snapshot"]
                    ),
                    observation_hash=existing["observation_hash"],
                    acceptable_by_action=json.loads(existing["acceptable_by_action"]),
                    selected_action_id=existing["selected_action_id"],
                    preferred_action_ids=(
                        json.loads(existing["preferred_action_ids"])
                        if existing["preferred_action_ids"]
                        else None
                    ),
                    reason=existing["reason"],
                    selection_acceptability_override=bool(
                        existing["selection_acceptability_override"]
                    ),
                    answered_at=existing["answered_at"],
                    deliberation_ms=existing["deliberation_ms"],
                    source=existing["source"],
                )
                row_out = conn.execute(
                    "SELECT * FROM outcomes WHERE trial_id = ?", (record.trial_id,)
                ).fetchone()
                existing_outcome = (
                    Outcome(
                        outcome_id=row_out["outcome_id"],
                        trial_id=row_out["trial_id"],
                        action_id=row_out["action_id"],
                        executed_payload=json.loads(row_out["executed_payload"]),
                        result_summary=json.loads(row_out["result_summary"]),
                        completed_at=row_out["completed_at"],
                    )
                    if row_out
                    else outcome
                )
                trial_row = conn.execute(
                    "SELECT state_version FROM trials WHERE trial_id = ?",
                    (record.trial_id,),
                ).fetchone()
                return existing_record, False, trial_row["state_version"], existing_outcome

            # 2. Check trial status and state version
            trial_row = conn.execute(
                "SELECT session_id, status, state_version, active_play_ms FROM trials WHERE trial_id = ?",
                (record.trial_id,),
            ).fetchone()
            if not trial_row:
                raise ValueError(f"Trial {record.trial_id} not found")
            if trial_row["status"] != "decision_open":
                raise ValueError(
                    f"Cannot commit decision for trial in status '{trial_row['status']}'; status must be 'decision_open'"
                )
            if trial_row["state_version"] != expected_state_version:
                raise ValueError(
                    f"State version conflict: expected {expected_state_version}, got {trial_row['state_version']}"
                )

            session_id = trial_row["session_id"]
            new_state_version = expected_state_version + 1

            # 3. Insert Decision
            conn.execute(
                """
                INSERT INTO decisions (
                    decision_id, trial_id, decision_index, public_observation_snapshot,
                    observation_hash, acceptable_by_action, selected_action_id,
                    preferred_action_ids, reason, selection_acceptability_override,
                    answered_at, deliberation_ms, source, idempotency_key, request_payload_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.decision_id,
                    record.trial_id,
                    record.decision_index,
                    json.dumps(record.public_observation_snapshot),
                    record.observation_hash,
                    json.dumps(record.acceptable_by_action),
                    record.selected_action_id,
                    (
                        json.dumps(record.preferred_action_ids)
                        if record.preferred_action_ids
                        else None
                    ),
                    record.reason,
                    1 if record.selection_acceptability_override else 0,
                    record.answered_at,
                    record.deliberation_ms,
                    record.source,
                    idempotency_key,
                    request_payload_hash,
                ),
            )

            # 4. Update Trial status and state
            conn.execute(
                """
                UPDATE trials
                SET public_state = ?, status = ?, state_version = ?
                WHERE trial_id = ?
                """,
                (
                    json.dumps(new_public_state),
                    new_status,
                    new_state_version,
                    record.trial_id,
                ),
            )

            # 5. Insert Outcome
            conn.execute(
                """
                INSERT INTO outcomes (outcome_id, trial_id, action_id, executed_payload, result_summary, completed_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    outcome.outcome_id,
                    outcome.trial_id,
                    outcome.action_id,
                    json.dumps(outcome.executed_payload),
                    json.dumps(outcome.result_summary),
                    outcome.completed_at,
                ),
            )

            # 6. Insert Event
            event_id = f"evt_{uuid.uuid4().hex[:12]}"
            timestamp = get_utc_now_iso()
            row_seq = conn.execute(
                "SELECT COALESCE(MAX(sequence_no), 0) + 1 AS next_seq FROM events WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            seq_no = row_seq["next_seq"]

            conn.execute(
                """
                INSERT INTO events (event_id, session_id, trial_id, sequence_no, timestamp_utc, event_type, payload, state_version_before, state_version_after)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    session_id,
                    record.trial_id,
                    seq_no,
                    timestamp,
                    "decision_committed",
                    json.dumps(event_payload),
                    expected_state_version,
                    new_state_version,
                ),
            )

            # 7. Atomically insert trial_ended event if trial reached terminal status
            terminal_statuses = ("completed", "completed_without_decision", "skipped", "aborted")
            if new_status in terminal_statuses:
                end_evt_id = f"evt_{uuid.uuid4().hex[:12]}"
                seq_no += 1
                conn.execute(
                    """
                    INSERT INTO events (event_id, session_id, trial_id, sequence_no, timestamp_utc, event_type, payload, state_version_before, state_version_after)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        end_evt_id,
                        session_id,
                        record.trial_id,
                        seq_no,
                        timestamp,
                        "trial_ended",
                        json.dumps({
                            "status": new_status,
                            "outcome_summary": outcome.result_summary,
                        }),
                        new_state_version,
                        new_state_version,
                    ),
                )

        return record, True, new_state_version, outcome

    def get_decision(self, trial_id: str) -> DecisionRecord | None:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM decisions WHERE trial_id = ?", (trial_id,)
            ).fetchone()
            if not row:
                return None
            return DecisionRecord(
                decision_id=row["decision_id"],
                trial_id=row["trial_id"],
                decision_index=row["decision_index"],
                public_observation_snapshot=json.loads(row["public_observation_snapshot"]),
                observation_hash=row["observation_hash"],
                acceptable_by_action=json.loads(row["acceptable_by_action"]),
                selected_action_id=row["selected_action_id"],
                preferred_action_ids=(
                    json.loads(row["preferred_action_ids"])
                    if row["preferred_action_ids"]
                    else None
                ),
                reason=row["reason"],
                selection_acceptability_override=bool(
                    row["selection_acceptability_override"]
                ),
                answered_at=row["answered_at"],
                deliberation_ms=row["deliberation_ms"],
                source=row["source"],
            )

    def record_outcome(self, outcome: Outcome) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO outcomes (outcome_id, trial_id, action_id, executed_payload, result_summary, completed_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(outcome_id) DO UPDATE SET
                    result_summary = excluded.result_summary,
                    completed_at = excluded.completed_at
                """,
                (
                    outcome.outcome_id,
                    outcome.trial_id,
                    outcome.action_id,
                    json.dumps(outcome.executed_payload),
                    json.dumps(outcome.result_summary),
                    outcome.completed_at,
                ),
            )

    def get_outcome(self, trial_id: str) -> Outcome | None:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM outcomes WHERE trial_id = ?", (trial_id,)
            ).fetchone()
            if not row:
                return None
            return Outcome(
                outcome_id=row["outcome_id"],
                trial_id=row["trial_id"],
                action_id=row["action_id"],
                executed_payload=json.loads(row["executed_payload"]),
                result_summary=json.loads(row["result_summary"]),
                completed_at=row["completed_at"],
            )

    def get_events_for_session(self, session_id: str) -> list[Event]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM events WHERE session_id = ? ORDER BY sequence_no ASC",
                (session_id,),
            ).fetchall()
            return [
                Event(
                    event_id=row["event_id"],
                    session_id=row["session_id"],
                    trial_id=row["trial_id"],
                    sequence_no=row["sequence_no"],
                    timestamp_utc=row["timestamp_utc"],
                    event_type=row["event_type"],
                    payload=json.loads(row["payload"]),
                    state_version_before=row["state_version_before"],
                    state_version_after=row["state_version_after"],
                )
                for row in rows
            ]

    def export_session_zip(self, session_id: str) -> bytes:
        """Export session into a canonical ZIP package according to Section 10.4 of PREFERENCE_LAB_SPEC.md.

        Files included:
        - manifest.json
        - instruments.json (strictly fetched by trial.instrument_hash)
        - decisions.json
        - events.jsonl
        - outcomes.json
        - private_replay.json
        """
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        trials = self.get_trials_for_session(session_id)
        events = self.get_events_for_session(session_id)

        decisions_list = []
        outcomes_list = []
        private_replay_list = []
        instruments_dict = {}

        for trial in trials:
            # Immutable instrument snapshot by hash
            inst = self.get_instrument_by_hash(trial.instrument_hash)
            if inst:
                instruments_dict[trial.instrument_hash] = inst.model_dump()

            # Decision
            dec = self.get_decision(trial.trial_id)
            if dec:
                decisions_list.append(dec.model_dump())

            # Outcome
            out = self.get_outcome(trial.trial_id)
            if out:
                outcomes_list.append(out.model_dump())

            # Private replay data
            tp = self.get_trial_private(trial.trial_id)
            private_replay_list.append(
                {
                    "trial_id": trial.trial_id,
                    "item_id": trial.item_id,
                    "instrument_hash": trial.instrument_hash,
                    "bomb_index": tp.bomb_index if tp else None,
                    "random_seed": tp.random_seed if tp else None,
                    "internal_state": tp.internal_state if tp else {},
                }
            )

        events_jsonl_lines = [canonical_json_str(evt.model_dump()) for evt in events]
        events_jsonl_content = "\n".join(events_jsonl_lines) + ("\n" if events_jsonl_lines else "")

        manifest_data = {
            "schema_version": "v001",
            "session_id": session.session_id,
            "participant_id": session.participant_id,
            "session_code": session.session_code,
            "mode": session.mode,
            "protocol_id": session.protocol_id,
            "protocol_version": session.protocol_version,
            "environment_order": session.environment_order,
            "exported_at": get_utc_now_iso(),
            "trial_count": len(trials),
            "decision_count": len(decisions_list),
            "event_count": len(events),
            "file_manifest": [
                "manifest.json",
                "instruments.json",
                "decisions.json",
                "events.jsonl",
                "outcomes.json",
                "private_replay.json",
            ],
        }

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", canonical_json_str(manifest_data))
            zf.writestr("instruments.json", canonical_json_str(instruments_dict))
            zf.writestr("decisions.json", canonical_json_str(decisions_list))
            zf.writestr("events.jsonl", events_jsonl_content)
            zf.writestr("outcomes.json", canonical_json_str(outcomes_list))
            zf.writestr("private_replay.json", canonical_json_str(private_replay_list))

        zip_buffer.seek(0)
        return zip_buffer.getvalue()
