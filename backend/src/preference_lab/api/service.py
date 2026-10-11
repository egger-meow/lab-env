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
        session_token = f"tok_{uuid.uuid4().hex}"
        now_iso = get_utc_now_iso()

        session = Session(
            session_id=session_id,
            participant_id=participant,
            session_code=session_code,
            session_token=session_token,
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

                    if is_tutorial:
                        bomb_seed = None
                        bomb_idx = None
                        fixed_demos = instrument.private_data.get("fixed_demonstrations", [])
                        comp_check = instrument.private_data.get("comprehension_check")
                        public_state = {
                            "num_boxes": n_boxes,
                            "reward_per_box": r_val,
                            "is_tutorial": True,
                            "tutorial_type": tut_type,
                            "fixed_demonstrations": fixed_demos,
                            "comprehension_check": {
                                "num_boxes": comp_check.get("num_boxes"),
                                "k": comp_check.get("k"),
                                "reward_per_box": comp_check.get("reward_per_box"),
                                "questions": [
                                    {
                                        "question_id": q["question_id"],
                                        "prompt": q["prompt"],
                                        "options": q["options"],
                                    }
                                    for q in comp_check.get("questions", [])
                                ],
                            } if comp_check else None,
                            "current_demonstration_index": 0,
                            "demonstrations_completed": False,
                            "comprehension_completed": False,
                            "selected_action_id": None,
                            "payoff": None,
                            "is_hit": None,
                            "bomb_revealed": False,
                        }
                        trial_private = TrialPrivate(
                            trial_id=trial_id,
                            bomb_index=None,
                            random_seed=None,
                            internal_state=instrument.private_data,
                        )
                    else:
                        bomb_seed = random.randint(1, 10000000)
                        bomb_idx = sample_bomb_index(n_boxes, seed=bomb_seed)

                        public_state = {
                            "num_boxes": n_boxes,
                            "reward_per_box": r_val,
                            "is_tutorial": False,
                            "tutorial_type": None,
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

        Uses immutable canonical hash snapshot to prevent template drift.
        Never leaks private answers, seeds, or unrevealed solutions.
        """
        trial = self.storage.get_trial(trial_id)
        if not trial:
            raise ValueError(f"Trial {trial_id} not found")

        instrument = self.storage.get_instrument_by_hash(trial.instrument_hash) or self.storage.get_instrument(trial.item_id)
        if not instrument:
            raise ValueError(f"Instrument {trial.item_id} (hash {trial.instrument_hash}) not found")

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

        # Time validation: cannot be negative or decrease
        if active_play_ms < 0:
            raise ValueError("active_play_ms cannot be negative")
        if active_play_ms < trial.active_play_ms:
            raise ValueError(f"active_play_ms cannot decrease: current {trial.active_play_ms}, received {active_play_ms}")

        instrument = self.storage.get_instrument_by_hash(trial.instrument_hash) or self.storage.get_instrument(trial.item_id)
        if not instrument:
            raise ValueError(f"Instrument {trial.item_id} not found")

        # Board validation: exact length and valid item IDs, no duplicates
        num_pos = instrument.public_stimulus["num_positions"]
        if len(board) != num_pos:
            raise ValueError(f"Board length must be {num_pos}, got {len(board)}")

        valid_items = set(instrument.public_stimulus["items"])
        placed_items = [x for x in board if x is not None]
        for item in placed_items:
            if item not in valid_items:
                raise ValueError(f"Invalid item '{item}' on board; valid items are: {sorted(valid_items)}")
        if len(placed_items) != len(set(placed_items)):
            raise ValueError(f"Duplicate items placed on board: {placed_items}")

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
        if is_solved:
            has_decision = (self.storage.get_decision(trial_id) is not None)
            new_status = "completed" if has_decision else "completed_without_decision"

        events = [("board_changed", {"board": board, "is_solved": is_solved, "status_message": msg})]
        new_version = self.storage.update_trial_state_atomic(
            trial_id=trial_id,
            public_state=public_state,
            status=new_status,
            active_play_ms=active_play_ms,
            expected_state_version=expected_state_version,
            events=events,
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

        if active_play_ms < 0:
            raise ValueError("active_play_ms cannot be negative")
        if active_play_ms < trial.active_play_ms:
            raise ValueError(f"active_play_ms cannot decrease: current {trial.active_play_ms}, received {active_play_ms}")

        instrument = self.storage.get_instrument_by_hash(trial.instrument_hash) or self.storage.get_instrument(trial.item_id)
        if instrument and instrument.private_data.get("is_tutorial", False):
            raise ValueError("Cannot open decision on tutorial trial. Tutorial trials require demonstration stepping or comprehension completion.")

        events = [("decision_opened", {"active_play_ms": active_play_ms})]
        new_version = self.storage.update_trial_state_atomic(
            trial_id=trial_id,
            public_state=trial.public_state,
            status="decision_open",
            active_play_ms=active_play_ms,
            expected_state_version=expected_state_version,
            events=events,
        )

        return {"status": "decision_open", "state_version": new_version}

    def commit_and_execute_decision(
        self,
        trial_id: str,
        idempotency_key: str,
        acceptable_by_action: dict[str, str],
        selected_action_id: str,
        deliberation_ms: int,
        state_version: int,
        preferred_action_ids: list[str] | None = None,
        reason: str | None = None,
        selection_acceptability_override: bool = False,
    ) -> dict[str, Any]:
        """Atomically commit participant decision and execute the corresponding action.

        Guards:
        - Checks idempotency key and request payload hash BEFORE action consequence derivation.
        - Verifies client-sent state_version against trial.state_version for new submissions.
        - Forbids submission on tutorial trials.
        - Enforces status == 'decision_open'.
        """
        request_payload_hash = sha256_canonical_json({
            "trial_id": trial_id,
            "acceptable_by_action": acceptable_by_action,
            "selected_action_id": selected_action_id,
            "preferred_action_ids": preferred_action_ids,
            "deliberation_ms": deliberation_ms,
            "selection_acceptability_override": selection_acceptability_override,
            "reason": reason,
        })

        # 1. Check idempotency FIRST before any action deduction / state checking
        existing = self.storage.get_decision_by_idempotency_key(idempotency_key)
        if existing is not None:
            existing_record, stored_payload_hash = existing
            if stored_payload_hash != request_payload_hash:
                raise ValueError("Idempotency key collision with different request payload")
            current_trial = self.storage.get_trial(trial_id)
            outcome = self.storage.get_outcome(trial_id)
            return {
                "idempotent": True,
                "decision": existing_record.model_dump(),
                "trial": current_trial.model_dump() if current_trial else None,
                "outcome": outcome.model_dump() if outcome else None,
            }

        # 2. For new submissions, validate trial status, client state_version, and tutorial isolation
        trial = self.storage.get_trial(trial_id)
        if not trial:
            raise ValueError(f"Trial {trial_id} not found")

        instrument = self.storage.get_instrument_by_hash(trial.instrument_hash) or self.storage.get_instrument(trial.item_id)
        if not instrument:
            raise ValueError(f"Instrument {trial.item_id} not found")

        if instrument.private_data.get("is_tutorial", False):
            raise ValueError("Cannot submit preference decision on tutorial trial. Tutorial trials require demonstration stepping or comprehension completion.")

        if trial.status != "decision_open":
            raise ValueError(f"Cannot commit decision for trial in status '{trial.status}'; status must be 'decision_open'")

        if state_version != trial.state_version:
            raise ValueError(f"State version conflict: expected {state_version}, got {trial.state_version}")

        valid_action_ids = [spec.action_id for spec in instrument.action_specs]

        # Independent observation snapshot complete with stimulus and action specs
        obs_snapshot = {
            "environment_id": trial.environment_id,
            "item_id": trial.item_id,
            "instrument_hash": trial.instrument_hash,
            "public_stimulus": instrument.public_stimulus,
            "action_specs": [spec.model_dump() for spec in instrument.action_specs],
            "display_order": trial.display_order,
            "public_state": trial.public_state,
            "active_play_ms": trial.active_play_ms,
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

        tp = self.storage.get_trial_private(trial_id)
        new_public_state = dict(trial.public_state)
        outcome_payload: dict[str, Any] = {}
        outcome_summary: dict[str, Any] = {}

        if trial.environment_id == "puzzle_hints":
            if selected_action_id == "continue":
                new_status = "active"
                outcome_summary = {"action": "continue", "info": "回到自主解謎"}
            elif selected_action_id == "hint":
                hint_text = instrument.private_data["hint_text"]
                new_public_state["revealed_hint"] = hint_text
                new_status = "active"
                outcome_summary = {"action": "hint", "revealed_hint": hint_text}
                outcome_payload = {"revealed_hint": hint_text}
            elif selected_action_id == "next_step":
                expected_sol = instrument.private_data["expected_solution"]
                pos, item, updated_board = execute_next_step(
                    expected_sol, new_public_state["board"]
                )
                new_public_state["board"] = updated_board
                revealed_steps = list(new_public_state.get("revealed_steps", []))
                revealed_steps.append({"position": pos, "item": item})
                new_public_state["revealed_steps"] = revealed_steps
                new_status = "active"
                outcome_summary = {"action": "next_step", "revealed_position": pos, "revealed_item": item}
                outcome_payload = {"position": pos, "item": item}
            elif selected_action_id == "solution":
                expected_sol = instrument.private_data["expected_solution"]
                new_public_state["board"] = list(expected_sol)
                new_public_state["is_solved"] = True
                new_status = "completed"
                outcome_summary = {"action": "solution", "solution": expected_sol}
                outcome_payload = {"solution": expected_sol}
            else:
                raise ValueError(f"Unknown puzzle action: {selected_action_id}")

        else:  # bret_discrete
            opts_map = {opt["action_id"]: opt["k"] for opt in instrument.public_stimulus["options"]}
            if selected_action_id not in opts_map:
                raise ValueError(f"Unknown BRET action: {selected_action_id}")
            k = opts_map[selected_action_id]
            n_boxes = instrument.public_stimulus["num_boxes"]
            r_val = instrument.public_stimulus["reward_per_box"]
            bomb_idx = tp.bomb_index if tp and tp.bomb_index is not None else 1

            payoff, is_hit = compute_bret_payoff(bomb_idx, k, r_val, n_boxes)

            new_public_state["selected_action_id"] = selected_action_id
            new_public_state["selected_k"] = k
            new_public_state["bomb_revealed"] = True
            new_public_state["bomb_index"] = bomb_idx
            new_public_state["payoff"] = payoff
            new_public_state["is_hit"] = is_hit
            new_status = "completed"

            outcome_payload = {"k": k, "bomb_index": bomb_idx}
            outcome_summary = {
                "k": k,
                "bomb_index": bomb_idx,
                "is_hit": is_hit,
                "payoff": payoff,
            }

        outcome_id = f"out_{uuid.uuid4().hex[:12]}"
        outcome = Outcome(
            outcome_id=outcome_id,
            trial_id=trial_id,
            action_id=selected_action_id,
            executed_payload=outcome_payload,
            result_summary=outcome_summary,
            completed_at=now_iso,
        )

        committed_record, is_new, new_ver, committed_outcome = self.storage.commit_decision_atomic(
            record=record,
            idempotency_key=idempotency_key,
            valid_action_ids=valid_action_ids,
            expected_state_version=trial.state_version,
            new_public_state=new_public_state,
            new_status=new_status,
            outcome=outcome,
            event_payload={
                "decision_id": record.decision_id,
                "selected_action_id": selected_action_id,
                "outcome_summary": outcome_summary,
            },
        )

        if not is_new:
            current_trial = self.storage.get_trial(trial_id)
            return {
                "idempotent": True,
                "decision": committed_record.model_dump(),
                "trial": current_trial.model_dump() if current_trial else None,
                "outcome": committed_outcome.model_dump() if committed_outcome else None,
            }

        return {
            "idempotent": False,
            "decision": committed_record.model_dump(),
            "trial_status": new_status,
            "state_version": new_ver,
            "public_state": new_public_state,
            "outcome": committed_outcome.model_dump(),
        }

    def next_trial(self, session_id: str, current_trial_id: str) -> dict[str, Any]:
        """Progress to the next trial in the session.

        Guards:
        - Current trial must be in terminal status (completed, completed_without_decision, skipped, aborted).
        - Idempotent: repeated calls return next trial without resetting its active_play_ms or state.
        """
        trials = self.storage.get_trials_for_session(session_id)
        current_idx = None
        current_trial = None
        for i, t in enumerate(trials):
            if t.trial_id == current_trial_id:
                current_idx = i
                current_trial = t
                break

        if current_idx is None or current_trial is None:
            raise ValueError(f"Trial {current_trial_id} not found in session {session_id}")

        terminal_statuses = ("completed", "completed_without_decision", "skipped", "aborted")
        if current_trial.status not in terminal_statuses:
            raise ValueError(
                f"Cannot advance to next trial: current trial {current_trial_id} is in status '{current_trial.status}', must be one of {terminal_statuses}"
            )

        next_idx = current_idx + 1
        if next_idx < len(trials):
            next_t = trials[next_idx]
            if next_t.status == "created":
                events = [("trial_started", {"collection_index": next_t.collection_index, "item_id": next_t.item_id})]
                new_ver = self.storage.update_trial_state_atomic(
                    trial_id=next_t.trial_id,
                    public_state=next_t.public_state,
                    status="active",
                    active_play_ms=0,
                    expected_state_version=next_t.state_version,
                    events=events,
                )
                return {"has_next": True, "next_trial_id": next_t.trial_id}
            else:
                # Idempotent replay: already activated or finished, do not reset active_play_ms!
                return {"has_next": True, "next_trial_id": next_t.trial_id}
        else:
            # Session completed
            with self.storage._get_connection() as conn:
                conn.execute(
                    "UPDATE sessions SET status = 'completed', completed_at = ? WHERE session_id = ?",
                    (get_utc_now_iso(), session_id),
                )
            return {"has_next": False, "session_completed": True}

    def pause_trial(
        self,
        trial_id: str,
        active_play_ms: int,
        expected_state_version: int,
    ) -> dict[str, Any]:
        trial = self.storage.get_trial(trial_id)
        if not trial:
            raise ValueError(f"Trial {trial_id} not found")
        if trial.status not in ("active", "decision_open"):
            raise ValueError(f"Cannot pause trial in status '{trial.status}'")

        if active_play_ms < 0:
            raise ValueError("active_play_ms cannot be negative")
        if active_play_ms < trial.active_play_ms:
            raise ValueError(f"active_play_ms cannot decrease: current {trial.active_play_ms}, received {active_play_ms}")

        public_state = dict(trial.public_state)
        public_state["pre_pause_status"] = trial.status
        events = [("trial_paused", {"active_play_ms": active_play_ms})]
        new_ver = self.storage.update_trial_state_atomic(
            trial_id=trial_id,
            public_state=public_state,
            status="paused",
            active_play_ms=active_play_ms,
            expected_state_version=expected_state_version,
            events=events,
        )
        return {"status": "paused", "state_version": new_ver}

    def resume_trial(
        self,
        trial_id: str,
        expected_state_version: int,
    ) -> dict[str, Any]:
        trial = self.storage.get_trial(trial_id)
        if not trial:
            raise ValueError(f"Trial {trial_id} not found")
        if trial.status != "paused":
            raise ValueError(f"Cannot resume trial in status '{trial.status}'; must be 'paused'")

        public_state = dict(trial.public_state)
        target_status = public_state.pop("pre_pause_status", "active")
        events = [("trial_resumed", {"resumed_to": target_status})]
        new_ver = self.storage.update_trial_state_atomic(
            trial_id=trial_id,
            public_state=public_state,
            status=target_status,
            active_play_ms=trial.active_play_ms,
            expected_state_version=expected_state_version,
            events=events,
        )
        return {"status": target_status, "state_version": new_ver}

    def skip_trial(
        self,
        trial_id: str,
        reason: str | None,
        active_play_ms: int,
        expected_state_version: int,
    ) -> dict[str, Any]:
        trial = self.storage.get_trial(trial_id)
        if not trial:
            raise ValueError(f"Trial {trial_id} not found")
        if trial.status in ("completed", "completed_without_decision", "skipped", "aborted"):
            raise ValueError(f"Trial already finished with status '{trial.status}'")

        if active_play_ms < 0:
            raise ValueError("active_play_ms cannot be negative")
        if active_play_ms < trial.active_play_ms:
            raise ValueError(f"active_play_ms cannot decrease: current {trial.active_play_ms}, received {active_play_ms}")

        events = [("trial_skipped", {"reason": reason, "active_play_ms": active_play_ms})]
        new_ver = self.storage.update_trial_state_atomic(
            trial_id=trial_id,
            public_state=trial.public_state,
            status="skipped",
            active_play_ms=active_play_ms,
            expected_state_version=expected_state_version,
            events=events,
        )
        return {"status": "skipped", "state_version": new_ver}

    def abort_trial(
        self,
        trial_id: str,
        reason: str | None,
        active_play_ms: int,
        expected_state_version: int,
    ) -> dict[str, Any]:
        trial = self.storage.get_trial(trial_id)
        if not trial:
            raise ValueError(f"Trial {trial_id} not found")
        if trial.status in ("completed", "completed_without_decision", "skipped", "aborted"):
            raise ValueError(f"Trial already finished with status '{trial.status}'")

        if active_play_ms < 0:
            raise ValueError("active_play_ms cannot be negative")
        if active_play_ms < trial.active_play_ms:
            raise ValueError(f"active_play_ms cannot decrease: current {trial.active_play_ms}, received {active_play_ms}")

        events = [("trial_aborted", {"reason": reason, "active_play_ms": active_play_ms})]
        new_ver = self.storage.update_trial_state_atomic(
            trial_id=trial_id,
            public_state=trial.public_state,
            status="aborted",
            active_play_ms=active_play_ms,
            expected_state_version=expected_state_version,
            events=events,
        )
        return {"status": "aborted", "state_version": new_ver}

    def step_demonstration(
        self,
        trial_id: str,
        step_index: int,
        expected_state_version: int,
    ) -> dict[str, Any]:
        trial = self.storage.get_trial(trial_id)
        if not trial:
            raise ValueError(f"Trial {trial_id} not found")

        # Demonstration can ONLY be stepped on active trial
        if trial.status != "active":
            raise ValueError(f"Demonstration can only be stepped when trial status is 'active', got '{trial.status}'")

        instrument = self.storage.get_instrument_by_hash(trial.instrument_hash) or self.storage.get_instrument(trial.item_id)
        if not instrument:
            raise ValueError("Instrument not found")
        if not instrument.private_data.get("is_tutorial"):
            raise ValueError("Not a tutorial trial")
        if instrument.private_data.get("tutorial_type") != "demonstration":
            raise ValueError("Not a demonstration tutorial")

        demos = instrument.private_data.get("fixed_demonstrations", [])
        if step_index < 0 or step_index >= len(demos):
            raise ValueError(f"Invalid demo step index {step_index}; total: {len(demos)}")

        # Enforce sequential stepping: cannot skip ahead
        current_step = trial.public_state.get("current_demonstration_index", 0)
        if step_index != current_step:
            raise ValueError(f"Demonstration must be stepped in sequential order: expected step_index {current_step}, got {step_index}")

        demo = demos[step_index]
        public_state = dict(trial.public_state)
        public_state["current_demonstration"] = demo
        public_state["current_demonstration_index"] = step_index + 1

        is_final = (step_index + 1 >= len(demos))
        new_status = "completed" if is_final else trial.status
        if is_final:
            public_state["demonstrations_completed"] = True

        events = [("demonstration_stepped", {"step_index": step_index, "is_final": is_final, "demo": demo})]
        new_ver = self.storage.update_trial_state_atomic(
            trial_id=trial_id,
            public_state=public_state,
            status=new_status,
            active_play_ms=trial.active_play_ms,
            expected_state_version=expected_state_version,
            events=events,
        )
        return {
            "status": new_status,
            "state_version": new_ver,
            "public_state": public_state,
            "demo": demo,
            "completed": is_final,
        }

    def submit_comprehension(
        self,
        trial_id: str,
        answers: dict[str, str],
        deliberation_ms: int,
        expected_state_version: int,
    ) -> dict[str, Any]:
        trial = self.storage.get_trial(trial_id)
        if not trial:
            raise ValueError(f"Trial {trial_id} not found")

        # Comprehension can ONLY be submitted on active trial
        if trial.status != "active":
            raise ValueError(f"Comprehension can only be submitted when trial status is 'active', got '{trial.status}'")

        if deliberation_ms < 0:
            raise ValueError("deliberation_ms cannot be negative")

        instrument = self.storage.get_instrument_by_hash(trial.instrument_hash) or self.storage.get_instrument(trial.item_id)
        if not instrument:
            raise ValueError("Instrument not found")
        if not instrument.private_data.get("is_tutorial"):
            raise ValueError("Not a tutorial trial")
        if instrument.private_data.get("tutorial_type") != "comprehension":
            raise ValueError("Not a comprehension tutorial")

        comp = instrument.private_data.get("comprehension_check", {})
        questions = comp.get("questions", [])
        if not questions:
            raise ValueError("No comprehension questions configured")

        feedback = []
        all_correct = True
        for q in questions:
            qid = q["question_id"]
            ans = answers.get(qid)
            correct_ans = q["correct_answer"]
            is_corr = (ans == correct_ans)
            if not is_corr:
                all_correct = False
            feedback.append({
                "question_id": qid,
                "submitted": ans,
                "correct": is_corr,
                "explanation": q["explanation"],
                "correct_answer": correct_ans,
            })

        public_state = dict(trial.public_state)
        public_state["comprehension_answers"] = answers
        public_state["comprehension_feedback"] = feedback
        public_state["comprehension_completed"] = all_correct

        new_status = "completed" if all_correct else trial.status
        events = [("comprehension_submitted", {"all_correct": all_correct, "deliberation_ms": deliberation_ms, "feedback": feedback})]
        new_ver = self.storage.update_trial_state_atomic(
            trial_id=trial_id,
            public_state=public_state,
            status=new_status,
            active_play_ms=trial.active_play_ms,
            expected_state_version=expected_state_version,
            events=events,
        )
        return {
            "status": new_status,
            "state_version": new_ver,
            "public_state": public_state,
            "all_correct": all_correct,
            "feedback": feedback,
        }

    def submit_trial_feedback(
        self,
        trial_id: str,
        feedback: dict[str, Any],
        expected_state_version: int,
    ) -> dict[str, Any]:
        trial = self.storage.get_trial(trial_id)
        if not trial:
            raise ValueError(f"Trial {trial_id} not found")

        public_state = dict(trial.public_state)
        public_state["feedback"] = feedback
        events = [("trial_feedback_submitted", feedback)]
        new_ver = self.storage.update_trial_state_atomic(
            trial_id=trial_id,
            public_state=public_state,
            status=trial.status,
            active_play_ms=trial.active_play_ms,
            expected_state_version=expected_state_version,
            events=events,
        )
        return {"status": trial.status, "state_version": new_ver, "feedback": feedback}

    def reveal_solution_followup(
        self,
        trial_id: str,
        expected_state_version: int,
    ) -> dict[str, Any]:
        trial = self.storage.get_trial(trial_id)
        if not trial:
            raise ValueError(f"Trial {trial_id} not found")
        if trial.status not in ("completed", "completed_without_decision", "skipped"):
            raise ValueError(f"Cannot reveal solution for unfinished trial in status '{trial.status}'")
        instrument = self.storage.get_instrument_by_hash(trial.instrument_hash) or self.storage.get_instrument(trial.item_id)
        if not instrument:
            raise ValueError("Instrument not found")
        if trial.environment_id != "puzzle_hints":
            raise ValueError("Solution reveal only supported for puzzle_hints")

        expected_sol = instrument.private_data.get("expected_solution")
        public_state = dict(trial.public_state)
        public_state["solution_revealed_followup"] = expected_sol
        events = [("solution_revealed_followup", {"solution": expected_sol})]
        new_ver = self.storage.update_trial_state_atomic(
            trial_id=trial_id,
            public_state=public_state,
            status=trial.status,
            active_play_ms=trial.active_play_ms,
            expected_state_version=expected_state_version,
            events=events,
        )
        return {
            "status": trial.status,
            "state_version": new_ver,
            "solution": expected_sol,
        }
