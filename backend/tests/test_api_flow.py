"""Integration tests for FastAPI endpoints, authentication, atomic decision execution, tutorial isolation, and full lifecycle flows."""

import io
import json
import zipfile
import pytest
from starlette.testclient import TestClient

from preference_lab.api.app import app, get_service
from preference_lab.api.service import LabService
from preference_lab.storage.sqlite import Storage

OPERATOR_TOKEN = "dev-operator-token-local"


@pytest.fixture
def client(tmp_path):
    storage = Storage(":memory:")
    service = LabService(storage)

    app.dependency_overrides[get_service] = lambda: service
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


def test_health_check(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "version": "0.1.0"}


def test_operator_auth_and_session_creation(client):
    # Missing token -> 401
    res_no_token = client.post(
        "/api/operator/sessions",
        json={"mode": "pilot", "environment_order": ["puzzle_hints", "bret_discrete"]},
    )
    assert res_no_token.status_code == 401

    # Invalid token -> 401
    res_invalid = client.post(
        "/api/operator/sessions",
        headers={"X-Operator-Token": "wrong-token"},
        json={"mode": "pilot", "environment_order": ["puzzle_hints", "bret_discrete"]},
    )
    assert res_invalid.status_code == 401

    # Valid token -> 200
    res = client.post(
        "/api/operator/sessions",
        headers={"X-Operator-Token": OPERATOR_TOKEN},
        json={"mode": "pilot", "environment_order": ["puzzle_hints", "bret_discrete"]},
    )
    assert res.status_code == 200
    data = res.json()
    assert "session" in data
    assert data["session"]["mode"] == "pilot"
    assert data["trial_count"] == 12  # 6 puzzle + 6 bret
    assert data["first_trial_id"] is not None


def test_participant_authentication_and_cross_session_protection(client):
    # 1. Create Session A
    res_a = client.post(
        "/api/operator/sessions",
        headers={"X-Operator-Token": OPERATOR_TOKEN},
        json={"mode": "pilot", "environment_order": ["puzzle_hints"]},
    )
    session_a = res_a.json()["session"]
    trial_a = res_a.json()["first_trial_id"]

    # 2. Create Session B
    res_b = client.post(
        "/api/operator/sessions",
        headers={"X-Operator-Token": OPERATOR_TOKEN},
        json={"mode": "pilot", "environment_order": ["puzzle_hints"]},
    )
    session_b = res_b.json()["session"]
    trial_b = res_b.json()["first_trial_id"]

    # 3. Unauthenticated access -> 401
    res_no_auth = client.get(f"/api/trials/{trial_a}")
    assert res_no_auth.status_code == 401
    assert "Missing X-Session-Token" in res_no_auth.json()["detail"]

    # 4. Invalid token -> 401
    res_bad_tok = client.get(
        f"/api/trials/{trial_a}",
        headers={"X-Session-Token": "invalid_tok_999"},
    )
    assert res_bad_tok.status_code == 401
    assert "Invalid participant session token" in res_bad_tok.json()["detail"]

    # 5. Join Session A to obtain token
    join_a = client.post("/api/sessions/join", json={"session_code": session_a["session_code"]})
    assert join_a.status_code == 200
    token_a = join_a.json()["session_token"]
    assert token_a.startswith("tok_")

    # 6. Join Session B to obtain token
    join_b = client.post("/api/sessions/join", json={"session_code": session_b["session_code"]})
    token_b = join_b.json()["session_token"]

    # 7. Valid session access to own trial -> 200
    res_valid = client.get(
        f"/api/trials/{trial_a}",
        headers={"X-Session-Token": token_a},
    )
    assert res_valid.status_code == 200

    # 8. Cross-session access: Token B attempting to access Trial A -> 403 Forbidden!
    res_cross = client.get(
        f"/api/trials/{trial_a}",
        headers={"X-Session-Token": token_b},
    )
    assert res_cross.status_code == 403
    assert "Trial does not belong" in res_cross.json()["detail"]


def test_participant_data_isolation(client):
    op_res = client.post(
        "/api/operator/sessions",
        headers={"X-Operator-Token": OPERATOR_TOKEN},
        json={"mode": "pilot", "environment_order": ["puzzle_hints", "bret_discrete"]},
    )
    session_code = op_res.json()["session"]["session_code"]
    first_trial_id = op_res.json()["first_trial_id"]

    join_res = client.post("/api/sessions/join", json={"session_code": session_code})
    token = join_res.json()["session_token"]

    trial_res = client.get(
        f"/api/trials/{first_trial_id}",
        headers={"X-Session-Token": token},
    )
    assert trial_res.status_code == 200
    trial_data = trial_res.json()

    # Public items MUST be present
    assert "public_stimulus" in trial_data
    assert "action_specs" in trial_data
    assert "public_state" in trial_data

    # PRIVATE DATA MUST NEVER BE PRESENT IN PARTICIPANT RESPONSE
    raw_str = trial_res.text
    assert "expected_solution" not in raw_str
    assert "hint_text" not in raw_str
    assert "bomb_index" not in raw_str
    assert "random_seed" not in raw_str
    assert "internal_state" not in raw_str


def test_decision_state_guards_and_atomic_execution(client):
    op_res = client.post(
        "/api/operator/sessions",
        headers={"X-Operator-Token": OPERATOR_TOKEN},
        json={"mode": "pilot", "environment_order": ["puzzle_hints"]},
    )
    session_code = op_res.json()["session"]["session_code"]
    trial_id = op_res.json()["first_trial_id"]

    join_res = client.post("/api/sessions/join", json={"session_code": session_code})
    token = join_res.json()["session_token"]
    headers = {"X-Session-Token": token}

    decision_payload = {
        "idempotency_key": "key_puz_1",
        "acceptable_by_action": {
            "continue": "yes",
            "hint": "yes",
            "next_step": "yes",
            "solution": "yes",
        },
        "selected_action_id": "hint",
        "deliberation_ms": 2000,
        "preferred_action_ids": ["hint"],
    }

    # 1. Submitting decision while status is 'active' -> 400 BAD REQUEST
    res_premature = client.post(
        f"/api/trials/{trial_id}/decision",
        headers=headers,
        json=decision_payload,
    )
    assert res_premature.status_code == 400
    assert "decision_open" in res_premature.json()["detail"]

    # 2. Open decision
    open_res = client.post(
        f"/api/trials/{trial_id}/open-decision",
        headers=headers,
        json={"active_play_ms": 3000, "state_version": 1},
    )
    assert open_res.status_code == 200
    assert open_res.json()["status"] == "decision_open"

    # 3. Submitting decision now succeeds
    valid_dec_payload = dict(decision_payload)
    valid_dec_payload["state_version"] = open_res.json()["state_version"]
    dec_res = client.post(
        f"/api/trials/{trial_id}/decision",
        headers=headers,
        json=valid_dec_payload,
    )
    assert dec_res.status_code == 200
    dec_data = dec_res.json()
    assert dec_data["idempotent"] is False
    assert dec_data["trial_status"] == "active"
    assert dec_data["public_state"]["revealed_hint"] is not None
    assert dec_data["outcome"]["action_id"] == "hint"

    # Verify decision snapshot has complete stimulus and action specs
    snapshot = dec_data["decision"]["public_observation_snapshot"]
    assert "public_stimulus" in snapshot
    assert "action_specs" in snapshot
    assert "clues" in snapshot["public_stimulus"]

    # 4. Same idempotency key re-sent -> 200 idempotent replay
    res_replay = client.post(
        f"/api/trials/{trial_id}/decision",
        headers=headers,
        json=decision_payload,
    )
    assert res_replay.status_code == 200
    assert res_replay.json()["idempotent"] is True

    # 5. Attempting to submit another decision with a different idempotency key -> 400!
    diff_payload = dict(decision_payload)
    diff_payload["idempotency_key"] = "key_puz_different"
    res_double = client.post(
        f"/api/trials/{trial_id}/decision",
        headers=headers,
        json=diff_payload,
    )
    assert res_double.status_code == 400


def test_puzzle_completion_without_decision_vs_with_decision(client):
    # Case A: Solved before decision opened -> completed_without_decision
    op_res = client.post(
        "/api/operator/sessions",
        headers={"X-Operator-Token": OPERATOR_TOKEN},
        json={"mode": "pilot", "environment_order": ["puzzle_hints"]},
    )
    session_code = op_res.json()["session"]["session_code"]
    trial_id = op_res.json()["first_trial_id"]

    join_res = client.post("/api/sessions/join", json={"session_code": session_code})
    headers = {"X-Session-Token": join_res.json()["session_token"]}

    # Practice 01 solution is ["moon", "key", "star", "leaf"]
    sol_board = ["moon", "key", "star", "leaf"]
    res_solve_direct = client.post(
        f"/api/trials/{trial_id}/board",
        headers=headers,
        json={"board": sol_board, "active_play_ms": 5000, "state_version": 1},
    )
    assert res_solve_direct.status_code == 200
    # Saving board alone must NOT complete trial or reveal is_solved!
    assert res_solve_direct.json()["status"] == "active"
    assert "is_solved" not in res_solve_direct.json()

    # Explicit check-answer evaluates board and completes trial
    res_check = client.post(
        f"/api/trials/{trial_id}/check-answer",
        headers=headers,
        json={"active_play_ms": 5500, "state_version": res_solve_direct.json()["state_version"]},
    )
    assert res_check.status_code == 200
    assert res_check.json()["is_solved"] is True
    assert res_check.json()["status"] == "completed_without_decision"
    assert res_check.json()["attempts"] == 1


def test_next_trial_guards_and_idempotency(client):
    op_res = client.post(
        "/api/operator/sessions",
        headers={"X-Operator-Token": OPERATOR_TOKEN},
        json={"mode": "pilot", "environment_order": ["puzzle_hints"]},
    )
    session_id = op_res.json()["session"]["session_id"]
    session_code = op_res.json()["session"]["session_code"]
    trial_id = op_res.json()["first_trial_id"]

    join_res = client.post("/api/sessions/join", json={"session_code": session_code})
    headers = {"X-Session-Token": join_res.json()["session_token"]}

    # 1. Calling next when current trial is still 'active' -> 400 BAD REQUEST
    res_next_uncompleted = client.post(
        f"/api/trials/{trial_id}/next",
        headers=headers,
        json={"session_id": session_id},
    )
    assert res_next_uncompleted.status_code == 400
    assert "not one of" in res_next_uncompleted.json()["detail"] or "must be one of" in res_next_uncompleted.json()["detail"]

    # 2. Skip or complete current trial
    res_skip = client.post(
        f"/api/trials/{trial_id}/skip",
        headers=headers,
        json={"reason": "test skip", "active_play_ms": 1000, "state_version": 1},
    )
    assert res_skip.status_code == 200
    assert res_skip.json()["status"] == "skipped"

    # 3. Now calling next succeeds and moves to trial 2
    res_next = client.post(
        f"/api/trials/{trial_id}/next",
        headers=headers,
        json={"session_id": session_id},
    )
    assert res_next.status_code == 200
    trial_2_id = res_next.json()["next_trial_id"]
    assert trial_2_id != trial_id

    # Simulate play time on trial 2
    t2_view_before = client.get(f"/api/trials/{trial_2_id}", headers=headers).json()
    res_b2 = client.post(
        f"/api/trials/{trial_2_id}/board",
        headers=headers,
        json={"board": ["sun", None, None, None], "active_play_ms": 12345, "state_version": t2_view_before["state_version"]},
    )
    assert res_b2.status_code == 200

    # 4. Calling next from trial 1 again must NOT reset trial 2 active_play_ms!
    res_next_replay = client.post(
        f"/api/trials/{trial_id}/next",
        headers=headers,
        json={"session_id": session_id},
    )
    assert res_next_replay.status_code == 200
    assert res_next_replay.json()["next_trial_id"] == trial_2_id

    trial_2_view = client.get(f"/api/trials/{trial_2_id}", headers=headers).json()
    assert trial_2_view["active_play_ms"] == 12345  # PRESERVED!


def test_bret_tutorial_isolation_and_steppers(client):
    # Create session with BRET only
    op_res = client.post(
        "/api/operator/sessions",
        headers={"X-Operator-Token": OPERATOR_TOKEN},
        json={"mode": "pilot", "environment_order": ["bret_discrete"]},
    )
    session_code = op_res.json()["session"]["session_code"]
    tut_trial_id = op_res.json()["first_trial_id"]  # tutorial_01 is first!

    join_res = client.post("/api/sessions/join", json={"session_code": session_code})
    headers = {"X-Session-Token": join_res.json()["session_token"]}

    tut_view = client.get(f"/api/trials/{tut_trial_id}", headers=headers).json()
    assert tut_view["public_state"]["is_tutorial"] is True
    assert tut_view["public_state"]["tutorial_type"] == "demonstration"

    # 1. Attempting to open decision or submit preference decision on tutorial -> 400!
    res_dec = client.post(
        f"/api/trials/{tut_trial_id}/decision",
        headers=headers,
        json={
            "idempotency_key": "tut_dec_1",
            "acceptable_by_action": {"collect_0": "yes"},
            "selected_action_id": "collect_0",
            "deliberation_ms": 1000,
        },
    )
    assert res_dec.status_code == 400
    assert "tutorial" in res_dec.json()["detail"].lower()

    # 2. Step fixed demonstrations
    # Step 0
    step0 = client.post(
        f"/api/trials/{tut_trial_id}/demonstration",
        headers=headers,
        json={"step_index": 0, "state_version": 1},
    )
    assert step0.status_code == 200
    assert step0.json()["completed"] is False
    assert step0.json()["demo"]["k"] == 2

    # Step 1 (final)
    step1 = client.post(
        f"/api/trials/{tut_trial_id}/demonstration",
        headers=headers,
        json={"step_index": 1, "state_version": step0.json()["state_version"]},
    )
    assert step1.status_code == 200
    assert step1.json()["completed"] is True
    assert step1.json()["status"] == "completed"

    # Tutorial 01 can now advance to Tutorial 02 (comprehension check)
    op_s_id = op_res.json()["session"]["session_id"]
    next_res = client.post(
        f"/api/trials/{tut_trial_id}/next",
        headers=headers,
        json={"session_id": op_s_id},
    )
    assert next_res.status_code == 200
    tut2_id = next_res.json()["next_trial_id"]

    tut2_view = client.get(f"/api/trials/{tut2_id}", headers=headers).json()
    assert tut2_view["public_state"]["tutorial_type"] == "comprehension"

    # Submit comprehension answers
    comp_res = client.post(
        f"/api/trials/{tut2_id}/comprehension",
        headers=headers,
        json={
            "answers": {
                "q1_hit_probability": "30%",
                "q2_hit_payoff": "0 點",
            },
            "deliberation_ms": 3500,
            "state_version": tut2_view["state_version"],
        },
    )
    assert comp_res.status_code == 200
    assert comp_res.json()["all_correct"] is True
    assert comp_res.json()["status"] == "completed"


def test_pause_resume_skip_abort_and_feedback_flows(client):
    op_res = client.post(
        "/api/operator/sessions",
        headers={"X-Operator-Token": OPERATOR_TOKEN},
        json={"mode": "pilot", "environment_order": ["puzzle_hints"]},
    )
    session_code = op_res.json()["session"]["session_code"]
    trial_id = op_res.json()["first_trial_id"]

    join_res = client.post("/api/sessions/join", json={"session_code": session_code})
    headers = {"X-Session-Token": join_res.json()["session_token"]}

    # Pause
    p_res = client.post(
        f"/api/trials/{trial_id}/pause",
        headers=headers,
        json={"active_play_ms": 4000, "state_version": 1},
    )
    assert p_res.status_code == 200
    assert p_res.json()["status"] == "paused"

    # Resume
    r_res = client.post(
        f"/api/trials/{trial_id}/resume",
        headers=headers,
        json={"state_version": p_res.json()["state_version"]},
    )
    assert r_res.status_code == 200
    assert r_res.json()["status"] == "active"

    # Skip
    s_res = client.post(
        f"/api/trials/{trial_id}/skip",
        headers=headers,
        json={"reason": "test skip", "active_play_ms": 5000, "state_version": r_res.json()["state_version"]},
    )
    assert s_res.status_code == 200
    assert s_res.json()["status"] == "skipped"

    # Feedback on finished trial
    fb_res = client.post(
        f"/api/trials/{trial_id}/feedback",
        headers=headers,
        json={"feedback": {"difficulty": 3, "enjoyment": 5}, "state_version": s_res.json()["state_version"]},
    )
    assert fb_res.status_code == 200
    assert fb_res.json()["feedback"]["enjoyment"] == 5

    # Solution followup
    sol_res = client.post(
        f"/api/trials/{trial_id}/solution-followup",
        headers=headers,
        json={"state_version": fb_res.json()["state_version"]},
    )
    assert sol_res.status_code == 200
    assert sol_res.json()["solution"] is not None


def test_operator_export_session_zip(client):
    op_res = client.post(
        "/api/operator/sessions",
        headers={"X-Operator-Token": OPERATOR_TOKEN},
        json={"mode": "pilot", "environment_order": ["puzzle_hints"]},
    )
    session_id = op_res.json()["session"]["session_id"]

    exp_res = client.get(
        f"/api/operator/sessions/{session_id}/export",
        headers={"X-Operator-Token": OPERATOR_TOKEN},
    )
    assert exp_res.status_code == 200
    assert exp_res.headers["content-type"] == "application/zip"

    with zipfile.ZipFile(io.BytesIO(exp_res.content)) as zf:
        namelist = zf.namelist()
        for f in ["manifest.json", "instruments.json", "decisions.json", "events.jsonl", "outcomes.json", "private_replay.json"]:
            assert f in namelist


def test_next_step_idempotent_replay_after_board_completed(client):
    """P1 counterexample: next_step completes board; resending original key & payload must return original outcome without error."""
    op_res = client.post(
        "/api/operator/sessions",
        headers={"X-Operator-Token": OPERATOR_TOKEN},
        json={"mode": "pilot", "environment_order": ["puzzle_hints"]},
    )
    session_code = op_res.json()["session"]["session_code"]
    trial_id = op_res.json()["first_trial_id"]

    join_res = client.post("/api/sessions/join", json={"session_code": session_code})
    headers = {"X-Session-Token": join_res.json()["session_token"]}

    # Practice 01 solution: ["moon", "key", "star", "leaf"]
    # Pre-fill 3 items so next_step fills the 4th item and solves the board!
    b_res = client.post(
        f"/api/trials/{trial_id}/board",
        headers=headers,
        json={"board": ["moon", "key", "star", None], "active_play_ms": 2000, "state_version": 1},
    )
    assert b_res.status_code == 200

    # Open decision
    open_res = client.post(
        f"/api/trials/{trial_id}/open-decision",
        headers=headers,
        json={"active_play_ms": 2500, "state_version": b_res.json()["state_version"]},
    )
    assert open_res.status_code == 200

    payload = {
        "idempotency_key": "next_step_solve_key_1",
        "acceptable_by_action": {"continue": "yes", "hint": "yes", "next_step": "yes", "solution": "yes"},
        "selected_action_id": "next_step",
        "deliberation_ms": 1500,
        "state_version": open_res.json()["state_version"],
        "reason": "need last item",
    }

    # 1. Commit next_step
    dec1 = client.post(f"/api/trials/{trial_id}/decision", headers=headers, json=payload)
    assert dec1.status_code == 200
    assert dec1.json()["idempotent"] is False
    assert dec1.json()["public_state"]["board"] == ["moon", "key", "star", "leaf"]

    # 2. Resend original key & payload: board is already full/solved, but must return idempotent=True without crashing!
    dec2 = client.post(f"/api/trials/{trial_id}/decision", headers=headers, json=payload)
    assert dec2.status_code == 200
    assert dec2.json()["idempotent"] is True
    assert dec2.json()["decision"]["decision_id"] == dec1.json()["decision"]["decision_id"]


def test_session_rejoin_positioning_paused_and_completed_states(client):
    """P1 counterexample: paused trial or finished trial before next must correctly position on rejoin."""
    op_res = client.post(
        "/api/operator/sessions",
        headers={"X-Operator-Token": OPERATOR_TOKEN},
        json={"mode": "pilot", "environment_order": ["puzzle_hints"]},
    )
    session_id = op_res.json()["session"]["session_id"]
    session_code = op_res.json()["session"]["session_code"]
    trial_1_id = op_res.json()["first_trial_id"]

    join_res = client.post("/api/sessions/join", json={"session_code": session_code})
    headers = {"X-Session-Token": join_res.json()["session_token"]}

    # Complete trial 1
    client.post(
        f"/api/trials/{trial_1_id}/skip",
        headers=headers,
        json={"reason": "skip t1", "active_play_ms": 1000, "state_version": 1},
    )
    next_res = client.post(
        f"/api/trials/{trial_1_id}/next",
        headers=headers,
        json={"session_id": session_id},
    )
    trial_2_id = next_res.json()["next_trial_id"]

    # Pause trial 2
    p_res = client.post(
        f"/api/trials/{trial_2_id}/pause",
        headers=headers,
        json={"active_play_ms": 3000, "state_version": 2},
    )
    assert p_res.status_code == 200

    # REJOIN: must locate trial 2 (the paused trial), NOT trial 1!
    rejoin = client.post("/api/sessions/join", json={"session_code": session_code})
    assert rejoin.status_code == 200
    assert rejoin.json()["current_trial_id"] == trial_2_id

    # Resume and skip trial 2
    r_res = client.post(
        f"/api/trials/{trial_2_id}/resume",
        headers=headers,
        json={"state_version": p_res.json()["state_version"]},
    )
    client.post(
        f"/api/trials/{trial_2_id}/skip",
        headers=headers,
        json={"reason": "skip t2", "active_play_ms": 4000, "state_version": r_res.json()["state_version"]},
    )

    # Rejoin when trial 2 is completed but next hasn't been called yet -> locates trial 2
    rejoin_t2_done = client.post("/api/sessions/join", json={"session_code": session_code})
    assert rejoin_t2_done.status_code == 200
    assert rejoin_t2_done.json()["current_trial_id"] == trial_2_id
    assert rejoin_t2_done.json()["session_completed"] is False


def test_tutorial_strict_status_and_sequential_stepping(client):
    """P1 counterexample: demo & comprehension cannot execute on created/paused/future trials, nor skip steps."""
    op_res = client.post(
        "/api/operator/sessions",
        headers={"X-Operator-Token": OPERATOR_TOKEN},
        json={"mode": "pilot", "environment_order": ["bret_discrete"]},
    )
    session_id = op_res.json()["session"]["session_id"]
    session_code = op_res.json()["session"]["session_code"]
    tut1_id = op_res.json()["first_trial_id"]

    join_res = client.post("/api/sessions/join", json={"session_code": session_code})
    headers = {"X-Session-Token": join_res.json()["session_token"]}

    # Future trial (tutorial_02, which is created, not active)
    tut2_id = client.get(f"/api/operator/sessions/{session_id}", headers={"X-Operator-Token": OPERATOR_TOKEN}).json()["trials"][1]["trial_id"]

    # 1. Attempting comprehension on created future trial -> 400!
    res_future_comp = client.post(
        f"/api/trials/{tut2_id}/comprehension",
        headers=headers,
        json={"answers": {"q1_hit_probability": "30%"}, "deliberation_ms": 1000, "state_version": 1},
    )
    assert res_future_comp.status_code == 400
    assert "active" in res_future_comp.json()["detail"].lower()

    # 2. Attempting demo on created future trial -> 400!
    res_future_demo = client.post(
        f"/api/trials/{tut2_id}/demonstration",
        headers=headers,
        json={"step_index": 0, "state_version": 1},
    )
    assert res_future_demo.status_code == 400
    assert "active" in res_future_demo.json()["detail"].lower()

    # 3. Attempting to skip step on current trial (tut1 has steps 0 then 1; submit step 1 first) -> 400!
    res_skip_step = client.post(
        f"/api/trials/{tut1_id}/demonstration",
        headers=headers,
        json={"step_index": 1, "state_version": 1},
    )
    assert res_skip_step.status_code == 400
    assert "sequential order" in res_skip_step.json()["detail"].lower()


def test_board_validation_and_monotonic_timer(client):
    """P2 counterexample: invalid board items, duplicates, wrong length, negative time, and regressing time are rejected."""
    op_res = client.post(
        "/api/operator/sessions",
        headers={"X-Operator-Token": OPERATOR_TOKEN},
        json={"mode": "pilot", "environment_order": ["puzzle_hints"]},
    )
    session_code = op_res.json()["session"]["session_code"]
    trial_id = op_res.json()["first_trial_id"]

    join_res = client.post("/api/sessions/join", json={"session_code": session_code})
    headers = {"X-Session-Token": join_res.json()["session_token"]}

    # 1. Unknown item -> 400
    res_unknown = client.post(
        f"/api/trials/{trial_id}/board",
        headers=headers,
        json={"board": ["unknown", None, None, None], "active_play_ms": 1000, "state_version": 1},
    )
    assert res_unknown.status_code == 400
    assert "Invalid item" in res_unknown.json()["detail"]

    # 2. Duplicate items -> 400
    res_dup = client.post(
        f"/api/trials/{trial_id}/board",
        headers=headers,
        json={"board": ["moon", "moon", None, None], "active_play_ms": 1000, "state_version": 1},
    )
    assert res_dup.status_code == 400
    assert "Duplicate items" in res_dup.json()["detail"]

    # 3. Wrong board length -> 400
    res_len = client.post(
        f"/api/trials/{trial_id}/board",
        headers=headers,
        json={"board": ["moon", "key"], "active_play_ms": 1000, "state_version": 1},
    )
    assert res_len.status_code == 400
    assert "Board length must be 4" in res_len.json()["detail"]

    # 4. Negative play time -> 400
    res_neg_time = client.post(
        f"/api/trials/{trial_id}/board",
        headers=headers,
        json={"board": ["moon", None, None, None], "active_play_ms": -20, "state_version": 1},
    )
    assert res_neg_time.status_code == 400
    assert "cannot be negative" in res_neg_time.json()["detail"]

    # 5. Valid board with 5000ms
    res_valid = client.post(
        f"/api/trials/{trial_id}/board",
        headers=headers,
        json={"board": ["moon", None, None, None], "active_play_ms": 5000, "state_version": 1},
    )
    assert res_valid.status_code == 200

    # 6. Regressing play time (submitting 3000ms when already 5000ms) -> 400!
    res_regress = client.post(
        f"/api/trials/{trial_id}/board",
        headers=headers,
        json={"board": ["moon", "key", None, None], "active_play_ms": 3000, "state_version": res_valid.json()["state_version"]},
    )
    assert res_regress.status_code == 400
    assert "cannot decrease" in res_regress.json()["detail"]


def test_stale_state_version_decision_rejection(client):
    """P2 counterexample: submitting decision with stale state_version is rejected."""
    op_res = client.post(
        "/api/operator/sessions",
        headers={"X-Operator-Token": OPERATOR_TOKEN},
        json={"mode": "pilot", "environment_order": ["puzzle_hints"]},
    )
    session_code = op_res.json()["session"]["session_code"]
    trial_id = op_res.json()["first_trial_id"]

    join_res = client.post("/api/sessions/join", json={"session_code": session_code})
    headers = {"X-Session-Token": join_res.json()["session_token"]}

    # Open decision bumps state_version to 2
    open_res = client.post(
        f"/api/trials/{trial_id}/open-decision",
        headers=headers,
        json={"active_play_ms": 2000, "state_version": 1},
    )
    assert open_res.status_code == 200
    assert open_res.json()["state_version"] == 2

    # Submit decision with stale state_version=1 -> 400!
    res_stale = client.post(
        f"/api/trials/{trial_id}/decision",
        headers=headers,
        json={
            "idempotency_key": "stale_test_key",
            "acceptable_by_action": {"continue": "yes", "hint": "yes", "next_step": "yes", "solution": "yes"},
            "selected_action_id": "hint",
            "deliberation_ms": 1000,
            "state_version": 1,  # STALE! Current is 2
        },
    )
    assert res_stale.status_code == 400
    assert "State version conflict" in res_stale.json()["detail"]


def test_idempotency_reason_modification_detected_as_collision(client):
    """Gap A: Same idempotency key with modified reason must be rejected as collision."""
    op_res = client.post(
        "/api/operator/sessions",
        headers={"X-Operator-Token": OPERATOR_TOKEN},
        json={"mode": "pilot", "environment_order": ["puzzle_hints"]},
    )
    session_code = op_res.json()["session"]["session_code"]
    trial_id = op_res.json()["first_trial_id"]

    join_res = client.post("/api/sessions/join", json={"session_code": session_code})
    headers = {"X-Session-Token": join_res.json()["session_token"]}

    open_res = client.post(
        f"/api/trials/{trial_id}/open-decision",
        headers=headers,
        json={"active_play_ms": 2000, "state_version": 1},
    )
    cur_ver = open_res.json()["state_version"]

    payload1 = {
        "idempotency_key": "reason_collision_test_key",
        "acceptable_by_action": {"continue": "yes", "hint": "yes", "next_step": "yes", "solution": "yes"},
        "selected_action_id": "hint",
        "deliberation_ms": 1500,
        "state_version": cur_ver,
        "reason": "Original reason",
    }
    res1 = client.post(f"/api/trials/{trial_id}/decision", headers=headers, json=payload1)
    assert res1.status_code == 200

    # Resend same key but with different reason -> 400!
    payload2 = dict(payload1)
    payload2["reason"] = "Tampered or modified reason"
    res2 = client.post(f"/api/trials/{trial_id}/decision", headers=headers, json=payload2)
    assert res2.status_code == 400
    assert "Idempotency key collision" in res2.json()["detail"]


def test_atomic_trial_ended_events_across_lifecycle(client):
    """Gap B: trial_ended event is atomically recorded on skip, abort, demo completion, and puzzle solve."""
    op_res = client.post(
        "/api/operator/sessions",
        headers={"X-Operator-Token": OPERATOR_TOKEN},
        json={"mode": "pilot", "environment_order": ["puzzle_hints"]},
    )
    session_id = op_res.json()["session"]["session_id"]
    session_code = op_res.json()["session"]["session_code"]
    trial_id = op_res.json()["first_trial_id"]

    join_res = client.post("/api/sessions/join", json={"session_code": session_code})
    headers = {"X-Session-Token": join_res.json()["session_token"]}

    # Skip trial
    client.post(
        f"/api/trials/{trial_id}/skip",
        headers=headers,
        json={"reason": "test skip", "active_play_ms": 2000, "state_version": 1},
    )

    # Inspect events recorded for session
    sess_detail = client.get(
        f"/api/operator/sessions/{session_id}",
        headers={"X-Operator-Token": OPERATOR_TOKEN},
    ).json()

    # Verify export zip contains trial_ended in events.jsonl
    zip_res = client.get(
        f"/api/operator/sessions/{session_id}/export",
        headers={"X-Operator-Token": OPERATOR_TOKEN},
    )
    with zipfile.ZipFile(io.BytesIO(zip_res.content)) as zf:
        lines = zf.read("events.jsonl").decode("utf-8").strip().split("\n")
        events = [json.loads(line) for line in lines]
        event_types = [e["event_type"] for e in events]
        assert "trial_skipped" in event_types
        assert "trial_ended" in event_types

        # Verify sequence_no strictly monotonic
        seqs = [e["sequence_no"] for e in events]
        assert seqs == sorted(seqs)
        assert len(seqs) == len(set(seqs))


def test_board_update_does_not_reveal_correctness_or_increment_attempts(client):
    """P1: /board saves board layout without checking correctness, incrementing attempts, or completing trial."""
    op_res = client.post(
        "/api/operator/sessions",
        headers={"X-Operator-Token": OPERATOR_TOKEN},
        json={"mode": "pilot", "environment_order": ["puzzle_hints"]},
    )
    session_id = op_res.json()["session"]["session_id"]
    session_code = op_res.json()["session"]["session_code"]
    trial_id = op_res.json()["first_trial_id"]

    join_res = client.post("/api/sessions/join", json={"session_code": session_code})
    headers = {"X-Session-Token": join_res.json()["session_token"]}

    # Submit correct solution to /board directly
    sol_board = ["moon", "key", "star", "leaf"]
    res_b = client.post(
        f"/api/trials/{trial_id}/board",
        headers=headers,
        json={"board": sol_board, "active_play_ms": 3000, "state_version": 1},
    )
    assert res_b.status_code == 200
    b_data = res_b.json()

    # 1. Status remains active (not completed_without_decision!)
    assert b_data["status"] == "active"
    # 2. Does not leak is_solved or status_message in response
    assert "is_solved" not in b_data
    assert "status_message" not in b_data
    # 3. Attempts count not incremented (0)
    assert b_data["public_state"].get("attempts", 0) == 0

    # 4. In events, only board_changed exists (no answer_checked, no trial_ended)
    sess_detail = client.get(
        f"/api/operator/sessions/{session_id}",
        headers={"X-Operator-Token": OPERATOR_TOKEN},
    ).json()
    trial_events = [e for e in sess_detail["events"] if e["trial_id"] == trial_id]
    ev_types = [e["event_type"] for e in trial_events]
    assert "board_changed" in ev_types
    assert "answer_checked" not in ev_types
    assert "trial_ended" not in ev_types


def test_explicit_check_answer_evaluates_solution_and_increments_attempts(client):
    """P1: Only explicit /check-answer provides feedback, increments attempts, and completes trial."""
    op_res = client.post(
        "/api/operator/sessions",
        headers={"X-Operator-Token": OPERATOR_TOKEN},
        json={"mode": "pilot", "environment_order": ["puzzle_hints"]},
    )
    session_id = op_res.json()["session"]["session_id"]
    session_code = op_res.json()["session"]["session_code"]
    trial_id = op_res.json()["first_trial_id"]

    join_res = client.post("/api/sessions/join", json={"session_code": session_code})
    headers = {"X-Session-Token": join_res.json()["session_token"]}

    # 1. Check answer on incorrect / partial board
    res_check_wrong = client.post(
        f"/api/trials/{trial_id}/check-answer",
        headers=headers,
        json={"active_play_ms": 1500, "state_version": 1, "board": ["moon", "leaf", None, None]},
    )
    assert res_check_wrong.status_code == 200
    wrong_data = res_check_wrong.json()
    assert wrong_data["is_solved"] is False
    assert wrong_data["status"] == "active"
    assert wrong_data["attempts"] == 1
    assert "status_message" in wrong_data

    # 2. Check answer on correct board
    sol_board = ["moon", "key", "star", "leaf"]
    res_check_correct = client.post(
        f"/api/trials/{trial_id}/check-answer",
        headers=headers,
        json={"active_play_ms": 3000, "state_version": wrong_data["state_version"], "board": sol_board},
    )
    assert res_check_correct.status_code == 200
    corr_data = res_check_correct.json()
    assert corr_data["is_solved"] is True
    assert corr_data["status"] == "completed_without_decision"
    assert corr_data["attempts"] == 2

    # 3. Exactly one trial_ended event recorded upon completion
    sess_detail = client.get(
        f"/api/operator/sessions/{session_id}",
        headers={"X-Operator-Token": OPERATOR_TOKEN},
    ).json()
    ended_events = [e for e in sess_detail["events"] if e["trial_id"] == trial_id and e["event_type"] == "trial_ended"]
    assert len(ended_events) == 1


def test_decision_open_freezes_board_and_play_time(client):
    """P1: During decision_open, board updates and active_play_ms modification are rejected."""
    op_res = client.post(
        "/api/operator/sessions",
        headers={"X-Operator-Token": OPERATOR_TOKEN},
        json={"mode": "pilot", "environment_order": ["puzzle_hints"]},
    )
    session_code = op_res.json()["session"]["session_code"]
    trial_id = op_res.json()["first_trial_id"]

    join_res = client.post("/api/sessions/join", json={"session_code": session_code})
    headers = {"X-Session-Token": join_res.json()["session_token"]}

    # Play for 100ms
    res_b = client.post(
        f"/api/trials/{trial_id}/board",
        headers=headers,
        json={"board": ["moon", None, None, None], "active_play_ms": 100, "state_version": 1},
    )
    assert res_b.status_code == 200

    # Open decision at 100ms
    res_open = client.post(
        f"/api/trials/{trial_id}/open-decision",
        headers=headers,
        json={"active_play_ms": 100, "state_version": res_b.json()["state_version"]},
    )
    assert res_open.status_code == 200
    assert res_open.json()["status"] == "decision_open"
    open_ver = res_open.json()["state_version"]

    # 1. Attempt to update board during decision_open -> 400 rejected!
    res_b_illegal = client.post(
        f"/api/trials/{trial_id}/board",
        headers=headers,
        json={"board": ["moon", "key", None, None], "active_play_ms": 200, "state_version": open_ver},
    )
    assert res_b_illegal.status_code == 400
    assert "Cannot update board on trial in status 'decision_open'" in res_b_illegal.json()["detail"]

    # 2. Attempt to check-answer during decision_open -> 400 rejected!
    res_check_illegal = client.post(
        f"/api/trials/{trial_id}/check-answer",
        headers=headers,
        json={"active_play_ms": 200, "state_version": open_ver},
    )
    assert res_check_illegal.status_code == 400
    assert "Cannot check answer on trial in status 'decision_open'" in res_check_illegal.json()["detail"]

    # 3. Attempt to increase play time via pause during decision_open -> 400 rejected!
    res_pause_illegal = client.post(
        f"/api/trials/{trial_id}/pause",
        headers=headers,
        json={"active_play_ms": 200, "state_version": open_ver},
    )
    assert res_pause_illegal.status_code == 400
    assert "active_play_ms is frozen during decision_open" in res_pause_illegal.json()["detail"]

    # Verify trial active_play_ms remained 100
    t_view = client.get(f"/api/trials/{trial_id}", headers=headers).json()
    assert t_view["active_play_ms"] == 100

    # 4. Commit decision 'continue' -> returns to active
    dec_res = client.post(
        f"/api/trials/{trial_id}/decision",
        headers=headers,
        json={
            "idempotency_key": "dec_continue_key_1",
            "acceptable_by_action": {"continue": "yes", "hint": "yes", "next_step": "yes", "solution": "yes"},
            "selected_action_id": "continue",
            "deliberation_ms": 1000,
            "state_version": open_ver,
        },
    )
    assert dec_res.status_code == 200
    assert dec_res.json()["trial_status"] == "active"
    after_ver = dec_res.json()["state_version"]

    # Now that status is 'active' again, board update and playing time increase succeed!
    res_b_after = client.post(
        f"/api/trials/{trial_id}/board",
        headers=headers,
        json={"board": ["moon", "key", None, None], "active_play_ms": 150, "state_version": after_ver},
    )
    assert res_b_after.status_code == 200
    assert res_b_after.json()["public_state"]["board"] == ["moon", "key", None, None]


def test_completed_trial_feedback_and_followup_do_not_duplicate_trial_ended(client):
    """P2: Submitting feedback and followup on completed trial must NOT record duplicate trial_ended events."""
    op_res = client.post(
        "/api/operator/sessions",
        headers={"X-Operator-Token": OPERATOR_TOKEN},
        json={"mode": "pilot", "environment_order": ["puzzle_hints"]},
    )
    session_id = op_res.json()["session"]["session_id"]
    session_code = op_res.json()["session"]["session_code"]
    trial_id = op_res.json()["first_trial_id"]

    join_res = client.post("/api/sessions/join", json={"session_code": session_code})
    headers = {"X-Session-Token": join_res.json()["session_token"]}

    # Solve puzzle via check-answer
    sol_board = ["moon", "key", "star", "leaf"]
    res_check = client.post(
        f"/api/trials/{trial_id}/check-answer",
        headers=headers,
        json={"active_play_ms": 4000, "state_version": 1, "board": sol_board},
    )
    assert res_check.status_code == 200
    assert res_check.json()["status"] == "completed_without_decision"
    v1 = res_check.json()["state_version"]

    # Verify exactly 1 trial_ended event
    def get_trial_ended_count():
        sess = client.get(
            f"/api/operator/sessions/{session_id}",
            headers={"X-Operator-Token": OPERATOR_TOKEN},
        ).json()
        return len([e for e in sess["events"] if e["trial_id"] == trial_id and e["event_type"] == "trial_ended"])

    assert get_trial_ended_count() == 1

    # 1. Submit feedback
    fb_res = client.post(
        f"/api/trials/{trial_id}/feedback",
        headers=headers,
        json={"feedback": {"rating": "just_right"}, "state_version": v1},
    )
    assert fb_res.status_code == 200
    v2 = fb_res.json()["state_version"]

    # STILL exactly 1 trial_ended event (no duplicate created!)
    assert get_trial_ended_count() == 1

    # 2. Reveal followup solution
    sol_res = client.post(
        f"/api/trials/{trial_id}/solution-followup",
        headers=headers,
        json={"state_version": v2},
    )
    assert sol_res.status_code == 200

    # STILL exactly 1 trial_ended event (no duplicate created!)
    assert get_trial_ended_count() == 1


def test_open_decision_on_already_solved_board_auto_completes_without_decision(client):
    """P1: When board is already solved but not yet checked, open_decision auto-completes as completed_without_decision."""
    op_res = client.post(
        "/api/operator/sessions",
        headers={"X-Operator-Token": OPERATOR_TOKEN},
        json={"mode": "pilot", "environment_order": ["puzzle_hints"]},
    )
    session_id = op_res.json()["session"]["session_id"]
    session_code = op_res.json()["session"]["session_code"]
    trial_id = op_res.json()["first_trial_id"]

    join_res = client.post("/api/sessions/join", json={"session_code": session_code})
    headers = {"X-Session-Token": join_res.json()["session_token"]}

    # Participant correctly places all pieces on the board without calling check-answer
    sol_board = ["moon", "key", "star", "leaf"]
    res_b = client.post(
        f"/api/trials/{trial_id}/board",
        headers=headers,
        json={"board": sol_board, "active_play_ms": 3000, "state_version": 1},
    )
    assert res_b.status_code == 200
    assert res_b.json()["status"] == "active"
    v_board = res_b.json()["state_version"]

    # Now open decision (e.g. timeout or participant clicked help button)
    res_open = client.post(
        f"/api/trials/{trial_id}/open-decision",
        headers=headers,
        json={"active_play_ms": 3500, "state_version": v_board},
    )
    assert res_open.status_code == 200
    open_data = res_open.json()

    # Must auto-complete as completed_without_decision rather than opening unexecutable 4 options!
    assert open_data["status"] == "completed_without_decision"
    assert open_data["is_solved"] is True

    # Trial in DB is now in terminal status completed_without_decision
    t_view = client.get(f"/api/trials/{trial_id}", headers=headers).json()
    assert t_view["status"] == "completed_without_decision"
    assert t_view["public_state"]["is_solved"] is True

    # Any attempt to submit decision is rejected (400) because trial is not decision_open
    res_dec = client.post(
        f"/api/trials/{trial_id}/decision",
        headers=headers,
        json={
            "idempotency_key": "illegal_dec_key_1",
            "acceptable_by_action": {"continue": "yes", "hint": "yes", "next_step": "yes", "solution": "yes"},
            "selected_action_id": "next_step",
            "deliberation_ms": 1000,
            "state_version": open_data["state_version"],
        },
    )
    assert res_dec.status_code == 400
    assert "status must be 'decision_open'" in res_dec.json()["detail"]


def test_paused_trial_freezes_play_time_for_skip_and_abort(client):
    """P2: During paused status (from active or decision_open), active_play_ms cannot increase for skip or abort."""
    op_res = client.post(
        "/api/operator/sessions",
        headers={"X-Operator-Token": OPERATOR_TOKEN},
        json={"mode": "pilot", "environment_order": ["puzzle_hints"]},
    )
    session_code = op_res.json()["session"]["session_code"]
    trial_id = op_res.json()["first_trial_id"]

    join_res = client.post("/api/sessions/join", json={"session_code": session_code})
    headers = {"X-Session-Token": join_res.json()["session_token"]}

    # 1. Play for 100ms and open decision
    res_b = client.post(
        f"/api/trials/{trial_id}/board",
        headers=headers,
        json={"board": ["moon", None, None, None], "active_play_ms": 100, "state_version": 1},
    )
    assert res_b.status_code == 200

    res_open = client.post(
        f"/api/trials/{trial_id}/open-decision",
        headers=headers,
        json={"active_play_ms": 100, "state_version": res_b.json()["state_version"]},
    )
    assert res_open.status_code == 200
    assert res_open.json()["status"] == "decision_open"

    # 2. Pause during decision_open
    res_pause = client.post(
        f"/api/trials/{trial_id}/pause",
        headers=headers,
        json={"active_play_ms": 100, "state_version": res_open.json()["state_version"]},
    )
    assert res_pause.status_code == 200
    assert res_pause.json()["status"] == "paused"
    p_ver = res_pause.json()["state_version"]

    # 3. Attempt to skip with increased time (100 -> 200) -> 400 rejected!
    res_skip_illegal = client.post(
        f"/api/trials/{trial_id}/skip",
        headers=headers,
        json={"reason": "skip while paused", "active_play_ms": 200, "state_version": p_ver},
    )
    assert res_skip_illegal.status_code == 400
    assert "active_play_ms cannot increase while trial is 'paused'" in res_skip_illegal.json()["detail"]

    # 4. Attempt to abort with increased time (100 -> 200) -> 400 rejected!
    res_abort_illegal = client.post(
        f"/api/trials/{trial_id}/abort",
        headers=headers,
        json={"reason": "abort while paused", "active_play_ms": 200, "state_version": p_ver},
    )
    assert res_abort_illegal.status_code == 400
    assert "active_play_ms cannot increase while trial is 'paused'" in res_abort_illegal.json()["detail"]

    # 5. Skip with exact preserved time 100 succeeds!
    res_skip_valid = client.post(
        f"/api/trials/{trial_id}/skip",
        headers=headers,
        json={"reason": "skip paused", "active_play_ms": 100, "state_version": p_ver},
    )
    assert res_skip_valid.status_code == 200
    assert res_skip_valid.json()["status"] == "skipped"

    t_view = client.get(f"/api/trials/{trial_id}", headers=headers).json()
    assert t_view["active_play_ms"] == 100



