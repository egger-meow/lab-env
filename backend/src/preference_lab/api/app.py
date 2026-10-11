"""FastAPI REST application for Preference Lab according to PREFERENCE_LAB_SPEC.md."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from fastapi import Depends, FastAPI, HTTPException, Header, Response, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from preference_lab.api.service import LabService
from preference_lab.storage.sqlite import Storage

OPERATOR_TOKEN = os.environ.get("PREFERENCE_LAB_OPERATOR_TOKEN", "dev-operator-token-local")

app = FastAPI(
    title="Preference Lab API",
    version="0.1.0",
    description="Backend API for Puzzle Hints and BRET Discrete preference research environments",
)

# Enable CORS for local Vite development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Shared Storage and Service instance
_storage: Storage | None = None
_service: LabService | None = None


def get_service() -> LabService:
    global _storage, _service
    if _service is None:
        db_file = os.environ.get("PREFERENCE_LAB_DB", "data/local.sqlite3")
        if db_file != ":memory:":
            Path(db_file).parent.mkdir(parents=True, exist_ok=True)
        _storage = Storage(db_file)
        _service = LabService(_storage)
    return _service


def verify_operator_token(x_operator_token: str | None = Header(None)) -> None:
    if not x_operator_token or x_operator_token != OPERATOR_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing operator token",
        )


# --- Request & Response Models ---

class JoinSessionRequest(BaseModel):
    session_code: str


class UpdateBoardRequest(BaseModel):
    board: list[str | None]
    active_play_ms: int
    state_version: int


class OpenDecisionRequest(BaseModel):
    active_play_ms: int
    state_version: int


class CommitDecisionRequest(BaseModel):
    idempotency_key: str
    acceptable_by_action: dict[str, str]
    selected_action_id: str
    deliberation_ms: int
    preferred_action_ids: list[str] | None = None
    reason: str | None = None
    selection_acceptability_override: bool = False


class NextTrialRequest(BaseModel):
    session_id: str


class CreateSessionRequest(BaseModel):
    mode: str = "pilot"
    environment_order: list[str] = Field(
        default_factory=lambda: ["puzzle_hints", "bret_discrete"]
    )
    participant_id: str | None = None
    protocol_id: str = "pilot_v001"


# --- Health ---

@app.get("/api/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "version": "0.1.0"}


# --- Participant Routes ---

@app.post("/api/sessions/join")
def join_session(
    payload: JoinSessionRequest,
    service: LabService = Depends(get_service),
) -> dict[str, Any]:
    session = service.storage.get_session_by_code(payload.session_code.strip())
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session with code '{payload.session_code}' not found",
        )

    trials = service.storage.get_trials_for_session(session.session_id)
    # Find current active trial
    active_trial = next((t for t in trials if t.status in ("active", "decision_open")), None)
    if not active_trial and trials:
        active_trial = trials[0]

    return {
        "session": session.model_dump(),
        "current_trial_id": active_trial.trial_id if active_trial else None,
        "total_trials": len(trials),
    }


@app.get("/api/trials/{trial_id}")
def get_trial(
    trial_id: str,
    service: LabService = Depends(get_service),
) -> dict[str, Any]:
    try:
        return service.get_participant_trial_view(trial_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@app.post("/api/trials/{trial_id}/board")
def update_board(
    trial_id: str,
    payload: UpdateBoardRequest,
    service: LabService = Depends(get_service),
) -> dict[str, Any]:
    try:
        return service.update_puzzle_board(
            trial_id=trial_id,
            board=payload.board,
            active_play_ms=payload.active_play_ms,
            expected_state_version=payload.state_version,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/api/trials/{trial_id}/open-decision")
def open_decision(
    trial_id: str,
    payload: OpenDecisionRequest,
    service: LabService = Depends(get_service),
) -> dict[str, Any]:
    try:
        return service.open_decision(
            trial_id=trial_id,
            active_play_ms=payload.active_play_ms,
            expected_state_version=payload.state_version,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/api/trials/{trial_id}/decision")
def commit_decision(
    trial_id: str,
    payload: CommitDecisionRequest,
    service: LabService = Depends(get_service),
) -> dict[str, Any]:
    try:
        return service.commit_and_execute_decision(
            trial_id=trial_id,
            idempotency_key=payload.idempotency_key,
            acceptable_by_action=payload.acceptable_by_action,
            selected_action_id=payload.selected_action_id,
            deliberation_ms=payload.deliberation_ms,
            preferred_action_ids=payload.preferred_action_ids,
            reason=payload.reason,
            selection_acceptability_override=payload.selection_acceptability_override,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/api/trials/{trial_id}/next")
def next_trial(
    trial_id: str,
    payload: NextTrialRequest,
    service: LabService = Depends(get_service),
) -> dict[str, Any]:
    try:
        return service.next_trial(
            session_id=payload.session_id,
            current_trial_id=trial_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# --- Operator Routes (Protected by X-Operator-Token) ---

@app.post("/api/operator/sessions", dependencies=[Depends(verify_operator_token)])
def create_session_operator(
    payload: CreateSessionRequest,
    service: LabService = Depends(get_service),
) -> dict[str, Any]:
    try:
        session = service.create_session(
            mode=payload.mode,
            environment_order=payload.environment_order,
            participant_id=payload.participant_id,
            protocol_id=payload.protocol_id,
        )
        trials = service.storage.get_trials_for_session(session.session_id)
        return {
            "session": session.model_dump(),
            "trial_count": len(trials),
            "first_trial_id": trials[0].trial_id if trials else None,
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/api/operator/sessions", dependencies=[Depends(verify_operator_token)])
def list_sessions_operator(
    service: LabService = Depends(get_service),
) -> list[dict[str, Any]]:
    sessions = service.storage.list_sessions()
    return [s.model_dump() for s in sessions]


@app.get(
    "/api/operator/sessions/{session_id}",
    dependencies=[Depends(verify_operator_token)],
)
def get_session_operator(
    session_id: str,
    service: LabService = Depends(get_service),
) -> dict[str, Any]:
    session = service.storage.get_session(session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    trials = service.storage.get_trials_for_session(session_id)
    events = service.storage.get_events_for_session(session_id)

    trials_data = []
    for t in trials:
        t_dict = t.model_dump()
        t_dict["decision"] = service.storage.get_decision(t.trial_id)
        t_dict["outcome"] = service.storage.get_outcome(t.trial_id)
        trials_data.append(t_dict)

    return {
        "session": session.model_dump(),
        "trials": trials_data,
        "event_count": len(events),
    }


@app.get(
    "/api/operator/sessions/{session_id}/export",
    dependencies=[Depends(verify_operator_token)],
)
def export_session_zip_operator(
    session_id: str,
    service: LabService = Depends(get_service),
) -> Response:
    try:
        zip_bytes = service.storage.export_session_zip(session_id)
        return Response(
            content=zip_bytes,
            media_type="application/zip",
            headers={
                "Content-Disposition": f"attachment; filename=session_{session_id}_export.zip"
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
