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
    dec_res = client.post(
        f"/api/trials/{trial_id}/decision",
        headers=headers,
        json=decision_payload,
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
    assert res_solve_direct.json()["is_solved"] is True
    assert res_solve_direct.json()["status"] == "completed_without_decision"


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
        json={"board": ["moon", None, None, None], "active_play_ms": 12345, "state_version": t2_view_before["state_version"]},
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
