"""Integration tests for FastAPI endpoints, participant data isolation, and operator flows."""

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
    # Use isolated in-memory or temp SQLite database for test
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
    # Missing token -> 422 or 401
    res_no_token = client.post(
        "/api/operator/sessions",
        json={"mode": "pilot", "environment_order": ["puzzle_hints", "bret_discrete"]},
    )
    assert res_no_token.status_code in (401, 422)

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


def test_participant_join_and_data_isolation(client):
    # 1. Operator creates session
    op_res = client.post(
        "/api/operator/sessions",
        headers={"X-Operator-Token": OPERATOR_TOKEN},
        json={"mode": "pilot", "environment_order": ["puzzle_hints", "bret_discrete"]},
    )
    session_code = op_res.json()["session"]["session_code"]
    first_trial_id = op_res.json()["first_trial_id"]

    # 2. Participant joins
    join_res = client.post(
        "/api/sessions/join",
        json={"session_code": session_code},
    )
    assert join_res.status_code == 200
    join_data = join_res.json()
    assert join_data["current_trial_id"] == first_trial_id
    assert join_data["total_trials"] == 12

    # 3. Participant fetches trial view -> STRICT DATA ISOLATION VERIFICATION
    trial_res = client.get(f"/api/trials/{first_trial_id}")
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


def test_puzzle_trial_full_interaction_flow(client):
    # 1. Create session with puzzle first
    op_res = client.post(
        "/api/operator/sessions",
        headers={"X-Operator-Token": OPERATOR_TOKEN},
        json={"mode": "pilot", "environment_order": ["puzzle_hints"]},
    )
    trial_id = op_res.json()["first_trial_id"]

    # 2. Update board
    b_res = client.post(
        f"/api/trials/{trial_id}/board",
        json={
            "board": ["moon", None, None, None],
            "active_play_ms": 1500,
            "state_version": 1,
        },
    )
    assert b_res.status_code == 200
    assert b_res.json()["public_state"]["attempts"] == 1

    # 3. Open decision
    open_res = client.post(
        f"/api/trials/{trial_id}/open-decision",
        json={"active_play_ms": 3000, "state_version": 2},
    )
    assert open_res.status_code == 200
    assert open_res.json()["status"] == "decision_open"

    # 4. Commit decision selecting 'hint'
    dec_payload = {
        "idempotency_key": "idemp_test_001",
        "acceptable_by_action": {
            "continue": "yes",
            "hint": "yes",
            "next_step": "unsure",
            "solution": "no",
        },
        "selected_action_id": "hint",
        "preferred_action_ids": ["hint"],
        "reason": "想看方向提示",
        "selection_acceptability_override": False,
        "deliberation_ms": 4200,
    }
    dec_res = client.post(f"/api/trials/{trial_id}/decision", json=dec_payload)
    assert dec_res.status_code == 200
    dec_data = dec_res.json()
    assert dec_data["idempotent"] is False
    assert dec_data["trial_status"] == "active"
    assert dec_data["public_state"]["revealed_hint"] is not None

    # 5. Idempotent re-submission returns original result
    re_dec_res = client.post(f"/api/trials/{trial_id}/decision", json=dec_payload)
    assert re_dec_res.status_code == 200
    assert re_dec_res.json()["idempotent"] is True


def test_bret_trial_full_interaction_flow(client):
    # 1. Create session with BRET only
    op_res = client.post(
        "/api/operator/sessions",
        headers={"X-Operator-Token": OPERATOR_TOKEN},
        json={"mode": "pilot", "environment_order": ["bret_discrete"]},
    )
    trial_id = op_res.json()["first_trial_id"]

    # 2. Get trial view (BRET starts in active / can commit decision directly)
    t_res = client.get(f"/api/trials/{trial_id}")
    assert t_res.status_code == 200
    action_specs = t_res.json()["action_specs"]
    assert len(action_specs) == 4

    # 3. Commit decision
    dec_payload = {
        "idempotency_key": "idemp_bret_001",
        "acceptable_by_action": {
            action_specs[0]["action_id"]: "yes",
            action_specs[1]["action_id"]: "yes",
            action_specs[2]["action_id"]: "no",
            action_specs[3]["action_id"]: "no",
        },
        "selected_action_id": action_specs[1]["action_id"],
        "deliberation_ms": 2500,
        "selection_acceptability_override": False,
    }
    dec_res = client.post(f"/api/trials/{trial_id}/decision", json=dec_payload)
    assert dec_res.status_code == 200
    dec_data = dec_res.json()
    assert dec_data["trial_status"] == "completed"

    # Immediate feedback policy: bomb index, payoff, and is_hit revealed
    pub_state = dec_data["public_state"]
    assert pub_state["bomb_revealed"] is True
    assert isinstance(pub_state["bomb_index"], int)
    assert isinstance(pub_state["payoff"], int)
    assert isinstance(pub_state["is_hit"], bool)


def test_operator_export_session_zip(client):
    # 1. Create session
    op_res = client.post(
        "/api/operator/sessions",
        headers={"X-Operator-Token": OPERATOR_TOKEN},
        json={"mode": "pilot", "environment_order": ["puzzle_hints"]},
    )
    session_id = op_res.json()["session"]["session_id"]
    trial_id = op_res.json()["first_trial_id"]

    # 2. Perform one action to generate event & decision
    client.post(
        f"/api/trials/{trial_id}/open-decision",
        json={"active_play_ms": 2000, "state_version": 1},
    )
    client.post(
        f"/api/trials/{trial_id}/decision",
        json={
            "idempotency_key": "exp_key_1",
            "acceptable_by_action": {
                "continue": "yes",
                "hint": "yes",
                "next_step": "yes",
                "solution": "yes",
            },
            "selected_action_id": "continue",
            "deliberation_ms": 1500,
        },
    )

    # 3. Export ZIP via operator endpoint
    exp_res = client.get(
        f"/api/operator/sessions/{session_id}/export",
        headers={"X-Operator-Token": OPERATOR_TOKEN},
    )
    assert exp_res.status_code == 200
    assert exp_res.headers["content-type"] == "application/zip"

    # Verify ZIP structure and parse content
    with zipfile.ZipFile(io.BytesIO(exp_res.content)) as zf:
        namelist = zf.namelist()
        for expected in [
            "manifest.json",
            "instruments.json",
            "decisions.json",
            "events.jsonl",
            "outcomes.json",
            "private_replay.json",
        ]:
            assert expected in namelist

        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        assert manifest["session_id"] == session_id
        assert manifest["decision_count"] == 1
        assert manifest["event_count"] >= 2
