"""Delivery verifier rejects corrupt exports and replays real engine output on synthetic data."""
import json
from pathlib import Path
import runpy
import zipfile

import pytest

from preference_lab.api.service import LabService
from preference_lab.domain.bret import sample_bomb_index
from preference_lab.storage.sqlite import Storage

verify = runpy.run_path(str(Path(__file__).parents[1] / "scripts" / "verify_export.py"))["verify"]


def export_decision(tmp_path, action="hint", environment="puzzle_hints"):
    storage = Storage(":memory:")
    service = LabService(storage, decision_source="synthetic_mock")
    session = service.create_session(environment_order=[environment])
    trials = storage.get_trials_for_session(session.session_id)
    trial = trials[0]
    if environment == "bret_discrete":
        for _ in range(2):
            service.skip_trial(trial.trial_id, "synthetic_fixture", 0, trial.state_version)
            next_result = service.next_trial(session.session_id, trial.trial_id)
            trial = storage.get_trial(next_result["next_trial_id"])
    else:
        service.update_puzzle_board(trial.trial_id, [None, "moon", None, None], 1000, trial.state_version)
        trial = storage.get_trial(trial.trial_id)
    if trial.status == "active":
        service.open_decision(trial.trial_id, trial.active_play_ms, trial.state_version)
    trial = storage.get_trial(trial.trial_id)
    instrument = storage.get_instrument_by_hash(trial.instrument_hash)
    result = service.commit_and_execute_decision(
        trial_id=trial.trial_id, idempotency_key="delivery-fixture",
        acceptable_by_action={spec.action_id: "unsure" for spec in instrument.action_specs},
        selected_action_id=action, deliberation_ms=10, state_version=trial.state_version,
    )
    path = tmp_path / "synthetic.zip"
    path.write_bytes(storage.export_session_zip(session.session_id))
    return path, result, storage.get_trial_private(trial.trial_id)


@pytest.mark.parametrize("action", ["continue", "hint", "next_step", "solution"])
def test_export_verifier_puzzle_replay(tmp_path, action):
    path, _, _ = export_decision(tmp_path, action)
    assert verify(path, "synthetic_mock")["decisions"] == 1


@pytest.mark.parametrize("seed,hit", [(1, True), (42, False)])
def test_export_verifier_fixed_seed_bret(tmp_path, monkeypatch, seed, hit):
    # Override only the bomb draw; production remains random and stored once.
    monkeypatch.setattr("preference_lab.api.service.sample_bomb_index", lambda n, **kwargs: sample_bomb_index(n, seed=seed))
    path, result, private = export_decision(tmp_path, "collect_20", "bret_discrete")
    assert private.bomb_index == sample_bomb_index(100, seed=seed)
    assert result["outcome"]["result_summary"]["is_hit"] is hit
    assert verify(path, "synthetic_mock")["action_replay"] == "passed"


@pytest.mark.parametrize("target", ["instruments.json", "outcomes.json", "events.jsonl"])
def test_export_verifier_rejects_tampering(tmp_path, target):
    path, _, _ = export_decision(tmp_path)
    with zipfile.ZipFile(path) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    if target == "instruments.json":
        data = json.loads(files[target])
        next(iter(data.values()))["private_data"]["hint_text"] = "altered"
    elif target == "outcomes.json":
        data = json.loads(files[target])
        data[0]["executed_payload"]["revealed_hint"] = "altered"
    else:
        files[target] = b""
        data = None
    if data is not None:
        files[target] = json.dumps(data).encode()
    corrupt = tmp_path / "corrupt.zip"
    with zipfile.ZipFile(corrupt, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    with pytest.raises(ValueError):
        verify(corrupt)


def test_export_verifier_rejects_wrong_source(tmp_path):
    path, _, _ = export_decision(tmp_path)
    with pytest.raises(ValueError, match="Unexpected decision source"):
        verify(path, "human_gui")
