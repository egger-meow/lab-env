"""Core experiment and trial execution service according to PREFERENCE_LAB_SPEC.md."""

from __future__ import annotations

import json
import random
import uuid
from pathlib import Path
from typing import Any

from preference_lab.domain.bret import (
    compute_bret_payoff,
    sample_bomb_index,
)
from preference_lab.domain.canonical import (
    canonical_json_str,
    sha256_canonical_json,
)
from preference_lab.domain.puzzle import (
    check_board,
    execute_next_step,
)
from preference_lab.domain.schemas import (
    DecisionRecord,
    Instrument,
    Outcome,
    Session,
    Trial,
    TrialPrivate,
)
from preference_lab.domain.validation import (
    load_and_validate_instrument,
    validate_decision_record,
)
from preference_lab.storage.sqlite import Storage, get_utc_now_iso

cur = Path(__file__).resolve().parent
while cur.parent != cur and not (cur / "PREFERENCE_LAB_SPEC.md").exists():
    cur = cur.parent
REPO_ROOT = cur


class LabService:
    def __init__(self, storage: Storage, repo_root: Path | None = None):
        self.storage = storage
        self.repo_root = repo_root or REPO_ROOT

    def create_session(
        self,
        mode: str = "pilot",
        environment_order: list[str] | None = None,
        participant_id: str | None = None,
        protocol_id: str = "pilot_v001",
    ) -> Session:
        """Create a new experiment session and instantiate all trials from protocol."""
        if mode not in ("practice", "pilot"):
            # Formal mode is disabled in M1 per spec Section 3
            raise ValueError(f"M1 only supports 'practice' or 'pilot' mode, got '{mode}'")

        proto_path = self.repo_root / "protocols" / f"{protocol_id}.json"
        if not proto_path.exists():
            raise ValueError(f"Protocol file {proto_path} not found")

        with open(proto_path, "r", encoding="utf-8") as f:
            proto = json.load(f)

        env_order = environment_order or proto.get("default_environment_order", ["puzzle_hints", "bret_discrete"])
        protocol_hash = sha256_canonical_json(proto)

        session_id = f"sess_{uuid.uuid4().hex[:12]}"
        participant = participant_id or f"p_{uuid.uuid4().hex[:8]}"
        session_code = f"PL-{uuid.uuid4().hex[:4].upper()}"
        now_iso = get_utc_now_iso()

        session = Session(
            session_id=session_id,
            participant_id=participant,
            session_code=session_code,
            mode=mode,
            protocol_id=protocol_id,
            protocol_version=proto.get("protocol_version", "0.1.0"),
            environment_order=env_order,
            status="created",
            created_at=now_iso,
        )
        self.storage.create_session(session)

        # Build trials list in sequence
        collection_idx = 0
        trials_to_create = []

        for env_id in env_order:
            env_config = proto["environments"][env_id]
            # Practice items first, then pilot items
            item_ids = list(env_config["practice_items"]) + list(env_config["pilot_items"])

            for item_id in item_ids:
                inst_path = self.repo_root / "instruments" / env_id / "v001" / f"{item_id.replace('pz_', '').replace('bret_', '')}.json"
                if not inst_path.exists():
                    # Fallback to direct glob if filename differs
                    inst_candidates = list((self.repo_root / "instruments" / env_id / "v001").glob(f"*{item_id}*.json"))
                    if not inst_candidates:
                        raise FileNotFoundError(f"Cannot find instrument JSON for {item_id}")
                    inst_path = inst_candidates[0]

                instrument = load_and_validate_instrument(inst_path)
                inst_hash = self.storage.save_instrument(instrument)

                trial_id = f"tr_{uuid.uuid4().hex[:12]}"
                # Action display order shuffling with stable seed
                action_ids = [spec.action_id for spec in instrument.action_specs]
                display_rng = random.Random(f"{session_id}_{trial_id}_display")
                display_order = list(action_ids)
                display_rng.shuffle(display_order)

                if env_id == "puzzle_hints":
                    n_pos = instrument.public_stimulus["num_positions"]
                    public_state = {
                        "board": [None] * n_pos,
                        "revealed_hint": None,
                        "revealed_steps": [],
                        "is_solved": False,
                        "attempts": 0,
                        "status_message": "",
                    }
                    trial_private = TrialPrivate(
                        trial_id=trial_id,
                        internal_state=instrument.private_data,
                    )
                else:  # bret_discrete
                    n_boxes = instrument.public_stimulus["num_boxes"]
                    r_val = instrument.public_stimulus["reward_per_box"]
                    is_tutorial = instrument.private_data.get("is_tutorial", False)
                    tut_type = instrument.private_data.get("tutorial_type")

                    bomb_seed = random.randint(1, 10000000)
                    bomb_idx = sample_bomb_index(n_boxes, seed=bomb_seed)

                    public_state = {
                        "num_boxes": n_boxes,
                        "reward_per_box": r_val,
                        "is_tutorial": is_tutorial,
                        "tutorial_type": tut_type,
                        "selected_action_id": None,
                        "payoff": None,
                        "is_hit": None,
                        "bomb_revealed": False,
                    }
                    trial_private = TrialPrivate(
                        trial_id=trial_id,
                        bomb_index=bomb_idx,
                        random_seed=bomb_seed,
                        internal_state=instrument.private_data,
                    )

                status = "active" if collection_idx == 0 else "created"
                trial = Trial(
                    trial_id=trial_id,
                    session_id=session_id,
                    participant_id=participant,
                    environment_id=env_id,
                    item_id=item_id,
                    instrument_hash=inst_hash,
                    protocol_hash=protocol_hash,
                    collection_index=collection_idx,
                    status=status,
                    state_version=1,
                    public_state=public_state,
                    active_play_ms=0,
                    display_order=display_order,
                    created_at=now_iso,
                )
                self.storage.create_trial(trial, trial_private)

                if collection_idx == 0:
                    self.storage.add_event(
                        session_id=session_id,
                        trial_id=trial_id,
                        event_type="trial_started",
                        payload={"collection_index": 0, "item_id": item_id},
                        state_version_before=1,
                        state_version_after=1,
                    )

                collection_idx += 1

        return session

    def get_participant_trial_view(self, trial_id: str) -> dict[str, Any]:
        """Fetch trial and public stimulus with STRICT DATA ISOLATION.

        Never leaks private answers, seeds, or unrevealed solutions.
        """
        trial = self.storage.get_trial(trial_id)
        if not trial:
            raise ValueError(f"Trial {trial_id} not found")

        instrument = self.storage.get_instrument(trial.item_id)
        if not instrument:
            raise ValueError(f"Instrument {trial.item_id} not found")

        # Isolated public view
        return {
            "trial_id": trial.trial_id,
            "session_id": trial.session_id,
            "environment_id": trial.environment_id,
            "item_id": trial.item_id,
            "collection_index": trial.collection_index,
            "status": trial.status,
            "state_version": trial.state_version,
            "public_state": trial.public_state,
            "active_play_ms": trial.active_play_ms,
            "display_order": trial.display_order,
            "public_stimulus": instrument.public_stimulus,
            "action_specs": [spec.model_dump() for spec in instrument.action_specs],
            "language": instrument.language,
            "template_id": instrument.template_id,
        }

    def update_puzzle_board(
        self,
        trial_id: str,
        board: list[str | None],
        active_play_ms: int,
        expected_state_version: int,
    ) -> dict[str, Any]:
        trial = self.storage.get_trial(trial_id)
        if not trial:
            raise ValueError(f"Trial {trial_id} not found")
        if trial.status not in ("active", "decision_open"):
            raise ValueError(f"Cannot update board on trial in status '{trial.status}'")

        instrument = self.storage.get_instrument(trial.item_id)
        if not instrument:
            raise ValueError(f"Instrument {trial.item_id} not found")

        items = instrument.public_stimulus["items"]
        clues_raw = instrument.public_stimulus["clues"]
        from preference_lab.domain.puzzle import Clue
        clues = [Clue.model_validate(c) for c in clues_raw]

        is_solved, msg = check_board(items, board, clues)

        public_state = dict(trial.public_state)
        public_state["board"] = board
        public_state["attempts"] = public_state.get("attempts", 0) + 1
        public_state["status_message"] = msg
        public_state["is_solved"] = is_solved

        new_status = trial.status
        if is_solved and trial.status == "active":
            # Solved before decision opened!
            new_status = "completed_without_decision"

        new_version = self.storage.update_trial_state(
            trial_id=trial_id,
            public_state=public_state,
            status=new_status,
            active_play_ms=active_play_ms,
            expected_state_version=expected_state_version,
        )

        self.storage.add_event(
            session_id=trial.session_id,
            trial_id=trial_id,
            event_type="board_changed",
            payload={"board": board, "is_solved": is_solved, "status_message": msg},
            state_version_before=expected_state_version,
            state_version_after=new_version,
        )

        return {
            "status": new_status,
            "state_version": new_version,
            "public_state": public_state,
            "is_solved": is_solved,
            "status_message": msg,
        }

    def open_decision(
        self,
        trial_id: str,
        active_play_ms: int,
        expected_state_version: int,
    ) -> dict[str, Any]:
        """Transition trial to decision_open upon request or timeout."""
        trial = self.storage.get_trial(trial_id)
        if not trial:
            raise ValueError(f"Trial {trial_id} not found")
        if trial.status != "active":
            raise ValueError(f"Trial status must be 'active' to open decision, got '{trial.status}'")

        new_version = self.storage.update_trial_state(
            trial_id=trial_id,
            public_state=trial.public_state,
            status="decision_open",
            active_play_ms=active_play_ms,
            expected_state_version=expected_state_version,
        )

        self.storage.add_event(
            session_id=trial.session_id,
            trial_id=trial_id,
            event_type="decision_opened",
            payload={"active_play_ms": active_play_ms},
            state_version_before=expected_state_version,
            state_version_after=new_version,
        )

        return {"status": "decision_open", "state_version": new_version}

    def commit_and_execute_decision(
        self,
        trial_id: str,
        idempotency_key: str,
        acceptable_by_action: dict[str, str],
        selected_action_id: str,
        deliberation_ms: int,
        preferred_action_ids: list[str] | None = None,
        reason: str | None = None,
        selection_acceptability_override: bool = False,
    ) -> dict[str, Any]:
        """Atomically commit participant decision and execute the corresponding action."""
        trial = self.storage.get_trial(trial_id)
        if not trial:
            raise ValueError(f"Trial {trial_id} not found")

        instrument = self.storage.get_instrument(trial.item_id)
        if not instrument:
            raise ValueError(f"Instrument {trial.item_id} not found")

        valid_action_ids = [spec.action_id for spec in instrument.action_specs]

        # Snapshot observation before consequence is revealed
        obs_snapshot = {
            "environment_id": trial.environment_id,
            "item_id": trial.item_id,
            "public_state": trial.public_state,
            "active_play_ms": trial.active_play_ms,
            "display_order": trial.display_order,
        }
        obs_hash = sha256_canonical_json(obs_snapshot)

        decision_id = f"dec_{uuid.uuid4().hex[:12]}"
        now_iso = get_utc_now_iso()

        record = DecisionRecord(
            decision_id=decision_id,
            trial_id=trial_id,
            decision_index=1,
            public_observation_snapshot=obs_snapshot,
            observation_hash=obs_hash,
            acceptable_by_action=acceptable_by_action,
            selected_action_id=selected_action_id,
            preferred_action_ids=preferred_action_ids,
            reason=reason,
            selection_acceptability_override=selection_acceptability_override,
            answered_at=now_iso,
            deliberation_ms=deliberation_ms,
            source="human_gui",
        )

        committed_record, is_new = self.storage.commit_decision(
            record=record,
            idempotency_key=idempotency_key,
            valid_action_ids=valid_action_ids,
        )

        if not is_new:
            # Idempotent replay: return existing state
            outcome = self.storage.get_outcome(trial_id)
            current_trial = self.storage.get_trial(trial_id)
            return {
                "idempotent": True,
                "decision": committed_record.model_dump(),
                "trial": current_trial.model_dump() if current_trial else None,
                "outcome": outcome.model_dump() if outcome else None,
            }

        # Execute action on trial
        tp = self.storage.get_trial_private(trial_id)
        public_state = dict(trial.public_state)
        outcome_payload: dict[str, Any] = {}
        outcome_summary: dict[str, Any] = {}

        if trial.environment_id == "puzzle_hints":
            if selected_action_id == "continue":
                new_status = "active"
                outcome_summary = {"action": "continue", "info": "回到自主解謎"}
            elif selected_action_id == "hint":
                hint_text = instrument.private_data["hint_text"]
                public_state["revealed_hint"] = hint_text
                new_status = "active"
                outcome_summary = {"action": "hint", "revealed_hint": hint_text}
            elif selected_action_id == "next_step":
                expected_sol = instrument.private_data["expected_solution"]
                pos, item, updated_board = execute_next_step(
                    expected_sol, public_state["board"]
                )
                public_state["board"] = updated_board
                revealed_steps = list(public_state.get("revealed_steps", []))
                revealed_steps.append({"position": pos, "item": item})
                public_state["revealed_steps"] = revealed_steps
                new_status = "active"
                outcome_summary = {"action": "next_step", "revealed_position": pos, "revealed_item": item}
            elif selected_action_id == "solution":
                expected_sol = instrument.private_data["expected_solution"]
                public_state["board"] = list(expected_sol)
                public_state["is_solved"] = True
                new_status = "completed"
                outcome_summary = {"action": "solution", "solution": expected_sol}
            else:
                raise ValueError(f"Unknown puzzle action: {selected_action_id}")

        else:  # bret_discrete
            opts_map = {opt["action_id"]: opt["k"] for opt in instrument.public_stimulus["options"]}
            k = opts_map[selected_action_id]
            n_boxes = instrument.public_stimulus["num_boxes"]
            r_val = instrument.public_stimulus["reward_per_box"]
            bomb_idx = tp.bomb_index if tp else 1

            payoff, is_hit = compute_bret_payoff(bomb_idx, k, r_val, n_boxes)

            public_state["selected_action_id"] = selected_action_id
            public_state["selected_k"] = k
            public_state["bomb_revealed"] = True
            public_state["bomb_index"] = bomb_idx
            public_state["payoff"] = payoff
            public_state["is_hit"] = is_hit
            new_status = "completed"

            outcome_payload = {"k": k, "bomb_index": bomb_idx}
            outcome_summary = {
                "k": k,
                "bomb_index": bomb_idx,
                "is_hit": is_hit,
                "payoff": payoff,
            }

        new_version = self.storage.update_trial_state(
            trial_id=trial_id,
            public_state=public_state,
            status=new_status,
            active_play_ms=trial.active_play_ms,
            expected_state_version=trial.state_version,
        )

        outcome_id = f"out_{uuid.uuid4().hex[:12]}"
        outcome = Outcome(
            outcome_id=outcome_id,
            trial_id=trial_id,
            action_id=selected_action_id,
            executed_payload=outcome_payload,
            result_summary=outcome_summary,
            completed_at=now_iso,
        )
        self.storage.record_outcome(outcome)

        self.storage.add_event(
            session_id=trial.session_id,
            trial_id=trial_id,
            event_type="decision_committed",
            payload={"decision_id": committed_record.decision_id, "selected_action_id": selected_action_id},
            state_version_before=trial.state_version,
            state_version_after=new_version,
        )

        return {
            "idempotent": False,
            "decision": committed_record.model_dump(),
            "trial_status": new_status,
            "state_version": new_version,
            "public_state": public_state,
            "outcome": outcome.model_dump(),
        }

    def next_trial(self, session_id: str, current_trial_id: str) -> dict[str, Any]:
        """Progress to the next trial in the session."""
        trials = self.storage.get_trials_for_session(session_id)
        current_idx = None
        for i, t in enumerate(trials):
            if t.trial_id == current_trial_id:
                current_idx = i
                break

        if current_idx is None:
            raise ValueError(f"Trial {current_trial_id} not found in session {session_id}")

        next_idx = current_idx + 1
        if next_idx < len(trials):
            next_t = trials[next_idx]
            new_ver = self.storage.update_trial_state(
                trial_id=next_t.trial_id,
                public_state=next_t.public_state,
                status="active",
                active_play_ms=0,
                expected_state_version=next_t.state_version,
            )
            self.storage.add_event(
                session_id=session_id,
                trial_id=next_t.trial_id,
                event_type="trial_started",
                payload={"collection_index": next_t.collection_index, "item_id": next_t.item_id},
                state_version_before=next_t.state_version,
                state_version_after=new_ver,
            )
            return {"has_next": True, "next_trial_id": next_t.trial_id}
        else:
            # Session completed
            with self.storage._get_connection() as conn:
                conn.execute(
                    "UPDATE sessions SET status = 'completed', completed_at = ? WHERE session_id = ?",
                    (get_utc_now_iso(), session_id),
                )
            return {"has_next": False, "session_completed": True}
