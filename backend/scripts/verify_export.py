"""Check a session ZIP offline and replay committed action results; never writes data."""
import argparse
import json
import zipfile

from preference_lab.domain.bret import compute_bret_payoff
from preference_lab.domain.canonical import sha256_canonical_json
from preference_lab.domain.puzzle import execute_next_step


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify(path, expected_source=None):
    with zipfile.ZipFile(path) as archive:
        require(archive.testzip() is None, "ZIP CRC failed")
        manifest = json.loads(archive.read("manifest.json"))
        require(set(archive.namelist()) == set(manifest["file_manifest"]), "File manifest mismatch")
        instruments = json.loads(archive.read("instruments.json"))
        decisions = json.loads(archive.read("decisions.json"))
        outcomes = json.loads(archive.read("outcomes.json"))
        private = json.loads(archive.read("private_replay.json"))
        events = [json.loads(line) for line in archive.read("events.jsonl").splitlines() if line.strip()]
    require(len(private) == manifest["trial_count"], "Trial count mismatch")
    require(len(decisions) == manifest["decision_count"], "Decision count mismatch")
    require(len(events) == manifest["event_count"], "Event count mismatch")
    require(len({d["trial_id"] for d in decisions}) == len(decisions), "Duplicate trial decision")
    require(len({o["trial_id"] for o in outcomes}) == len(outcomes), "Duplicate trial outcome")
    require(len({p["trial_id"] for p in private}) == len(private), "Duplicate private trial")
    require([e["sequence_no"] for e in events] == list(range(1, len(events) + 1)), "Event sequence mismatch")
    for digest, instrument in instruments.items():
        require(sha256_canonical_json(instrument) == digest, "Instrument hash mismatch")
    private_by_trial = {p["trial_id"]: p for p in private}
    outcomes_by_trial = {o["trial_id"]: o for o in outcomes}
    require(set(outcomes_by_trial) == {d["trial_id"] for d in decisions}, "Decision/outcome mismatch")
    for entry in private:
        require(entry["instrument_hash"] in instruments, "Missing instrument snapshot")
    for event in events:
        require(event["session_id"] == manifest["session_id"], "Foreign session event")
        require(event["trial_id"] in private_by_trial, "Unknown event trial")
    for decision in decisions:
        trial_id = decision["trial_id"]
        snapshot = decision["public_observation_snapshot"]
        require(sha256_canonical_json(snapshot) == decision["observation_hash"], "Observation hash mismatch")
        if expected_source:
            require(decision["source"] == expected_source, "Unexpected decision source")
        entry = private_by_trial[trial_id]
        require(snapshot["instrument_hash"] == entry["instrument_hash"], "Trial instrument mismatch")
        instrument = instruments[entry["instrument_hash"]]
        action = decision["selected_action_id"]
        outcome = outcomes_by_trial[trial_id]
        require(outcome["action_id"] == action, "Outcome action mismatch")
        payload = outcome["executed_payload"]
        summary = outcome["result_summary"]
        if instrument["environment_id"] == "bret_discrete":
            stimulus = instrument["public_stimulus"]
            k = next(o["k"] for o in stimulus["options"] if o["action_id"] == action)
            bomb = entry["bomb_index"]
            payoff, hit = compute_bret_payoff(bomb, k, stimulus["reward_per_box"], stimulus["num_boxes"])
            require(payload == {"k": k, "bomb_index": bomb}, "BRET execution mismatch")
            require(summary == {"k": k, "bomb_index": bomb, "is_hit": hit, "payoff": payoff}, "BRET replay mismatch")
        elif action == "hint":
            require(payload == {"revealed_hint": instrument["private_data"]["hint_text"]}, "Hint replay mismatch")
        elif action == "solution":
            require(payload == {"solution": instrument["private_data"]["expected_solution"]}, "Solution replay mismatch")
        elif action == "next_step":
            position, item, _ = execute_next_step(instrument["private_data"]["expected_solution"], snapshot["public_state"]["board"])
            require(payload == {"position": position, "item": item}, "Next-step replay mismatch")
        else:
            require(action == "continue" and payload == {}, "Unknown puzzle action")
    return {"session_id": manifest["session_id"], "trials": len(private), "decisions": len(decisions),
            "events": len(events), "sources": sorted({d["source"] for d in decisions}), "action_replay": "passed"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("zip_path")
    parser.add_argument("--expected-source", choices=["human_gui", "human_import", "synthetic_mock"])
    args = parser.parse_args()
    print(json.dumps(verify(args.zip_path, args.expected_source), ensure_ascii=False))
