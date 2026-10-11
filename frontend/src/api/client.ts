import type {
  CommitDecisionResponse,
  EventRecord,
  JoinSessionResponse,
  ParticipantTrialView,
  SessionInfo,
} from '../types';

export class ApiError extends Error {
  status: number;
  detail: string;
  isStateVersionConflict: boolean;

  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
    this.isStateVersionConflict = detail.toLowerCase().includes('state version conflict');
  }
}

async function request<T>(url: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers || {});
  if (!headers.has('Content-Type') && options.body && typeof options.body === 'string') {
    headers.set('Content-Type', 'application/json');
  }

  const targetUrl =
    typeof window === 'undefined' && url.startsWith('/')
      ? `http://127.0.0.1:8000${url}`
      : url;

  const response = await fetch(targetUrl, { ...options, headers });
  if (!response.ok) {
    let errorDetail = `Request failed with status ${response.status}`;
    try {
      const errJson = await response.json();
      if (errJson && errJson.detail) {
        errorDetail = typeof errJson.detail === 'string' ? errJson.detail : JSON.stringify(errJson.detail);
      }
    } catch {
      // ignore JSON parse failure
    }
    throw new ApiError(response.status, errorDetail);
  }

  return response.json() as Promise<T>;
}

export const api = {
  // Participant endpoints
  async joinSession(sessionCode: string): Promise<JoinSessionResponse> {
    return request<JoinSessionResponse>('/api/sessions/join', {
      method: 'POST',
      body: JSON.stringify({ session_code: sessionCode }),
    });
  },

  async getTrial(trialId: string, sessionToken: string): Promise<ParticipantTrialView> {
    return request<ParticipantTrialView>(`/api/trials/${trialId}`, {
      method: 'GET',
      headers: { 'X-Session-Token': sessionToken },
    });
  },

  async updateBoard(
    trialId: string,
    board: (string | null)[],
    activePlayMs: number,
    stateVersion: number,
    sessionToken: string
  ): Promise<{ status: string; state_version: number; public_state: Record<string, any> }> {
    return request(`/api/trials/${trialId}/board`, {
      method: 'POST',
      headers: { 'X-Session-Token': sessionToken },
      body: JSON.stringify({
        board,
        active_play_ms: activePlayMs,
        state_version: stateVersion,
      }),
    });
  },

  async checkAnswer(
    trialId: string,
    activePlayMs: number,
    stateVersion: number,
    board?: (string | null)[],
    sessionToken?: string
  ): Promise<{
    status: string;
    state_version: number;
    public_state: Record<string, any>;
    is_solved: boolean;
    status_message: string;
    attempts: number;
  }> {
    return request(`/api/trials/${trialId}/check-answer`, {
      method: 'POST',
      headers: sessionToken ? { 'X-Session-Token': sessionToken } : {},
      body: JSON.stringify({
        active_play_ms: activePlayMs,
        state_version: stateVersion,
        board: board ?? null,
      }),
    });
  },

  async openDecision(
    trialId: string,
    activePlayMs: number,
    stateVersion: number,
    sessionToken: string
  ): Promise<{
    status: string;
    state_version: number;
    auto_completed?: boolean;
    is_solved?: boolean;
    public_state?: Record<string, any>;
  }> {
    return request(`/api/trials/${trialId}/open-decision`, {
      method: 'POST',
      headers: { 'X-Session-Token': sessionToken },
      body: JSON.stringify({
        active_play_ms: activePlayMs,
        state_version: stateVersion,
      }),
    });
  },

  async commitDecision(
    trialId: string,
    payload: {
      idempotency_key: string;
      acceptable_by_action: Record<string, string>;
      selected_action_id: string;
      preferred_action_ids?: string[];
      deliberation_ms: number;
      state_version: number;
      reason?: string;
      selection_acceptability_override?: boolean;
    },
    sessionToken: string
  ): Promise<CommitDecisionResponse> {
    return request<CommitDecisionResponse>(`/api/trials/${trialId}/decision`, {
      method: 'POST',
      headers: { 'X-Session-Token': sessionToken },
      body: JSON.stringify(payload),
    });
  },

  async nextTrial(
    trialId: string,
    sessionId: string,
    sessionToken: string
  ): Promise<{ has_next: boolean; next_trial_id?: string; session_completed?: boolean }> {
    return request(`/api/trials/${trialId}/next`, {
      method: 'POST',
      headers: { 'X-Session-Token': sessionToken },
      body: JSON.stringify({ session_id: sessionId }),
    });
  },

  async pauseTrial(
    trialId: string,
    activePlayMs: number,
    stateVersion: number,
    sessionToken: string
  ): Promise<{ status: string; state_version: number }> {
    return request(`/api/trials/${trialId}/pause`, {
      method: 'POST',
      headers: { 'X-Session-Token': sessionToken },
      body: JSON.stringify({ active_play_ms: activePlayMs, state_version: stateVersion }),
    });
  },

  async resumeTrial(
    trialId: string,
    stateVersion: number,
    sessionToken: string
  ): Promise<{ status: string; state_version: number }> {
    return request(`/api/trials/${trialId}/resume`, {
      method: 'POST',
      headers: { 'X-Session-Token': sessionToken },
      body: JSON.stringify({ state_version: stateVersion }),
    });
  },

  async skipTrial(
    trialId: string,
    reason: string | null,
    activePlayMs: number,
    stateVersion: number,
    sessionToken: string
  ): Promise<{ status: string; state_version: number }> {
    return request(`/api/trials/${trialId}/skip`, {
      method: 'POST',
      headers: { 'X-Session-Token': sessionToken },
      body: JSON.stringify({ reason, active_play_ms: activePlayMs, state_version: stateVersion }),
    });
  },

  async abortTrial(
    trialId: string,
    reason: string | null,
    activePlayMs: number,
    stateVersion: number,
    sessionToken: string
  ): Promise<{ status: string; state_version: number }> {
    return request(`/api/trials/${trialId}/abort`, {
      method: 'POST',
      headers: { 'X-Session-Token': sessionToken },
      body: JSON.stringify({ reason, active_play_ms: activePlayMs, state_version: stateVersion }),
    });
  },

  async stepDemonstration(
    trialId: string,
    stepIndex: number,
    stateVersion: number,
    sessionToken: string
  ): Promise<{ status: string; state_version: number; public_state: Record<string, any> }> {
    return request(`/api/trials/${trialId}/demonstration`, {
      method: 'POST',
      headers: { 'X-Session-Token': sessionToken },
      body: JSON.stringify({ step_index: stepIndex, state_version: stateVersion }),
    });
  },

  async submitComprehension(
    trialId: string,
    answers: Record<string, string>,
    deliberationMs: number,
    stateVersion: number,
    sessionToken: string
  ): Promise<{
    status: string;
    state_version: number;
    public_state: Record<string, any>;
    all_correct: boolean;
    feedback: Array<{ question_id: string; submitted: string; correct: boolean; explanation: string }>;
  }> {
    return request(`/api/trials/${trialId}/comprehension`, {
      method: 'POST',
      headers: { 'X-Session-Token': sessionToken },
      body: JSON.stringify({ answers, deliberation_ms: deliberationMs, state_version: stateVersion }),
    });
  },

  async submitFeedback(
    trialId: string,
    feedback: Record<string, any>,
    stateVersion: number,
    sessionToken: string
  ): Promise<{ status: string; state_version: number; feedback: Record<string, any> }> {
    return request(`/api/trials/${trialId}/feedback`, {
      method: 'POST',
      headers: { 'X-Session-Token': sessionToken },
      body: JSON.stringify({ feedback, state_version: stateVersion }),
    });
  },

  async revealSolutionFollowup(
    trialId: string,
    stateVersion: number,
    sessionToken: string
  ): Promise<{ status: string; state_version: number; solution: string[] }> {
    return request(`/api/trials/${trialId}/solution-followup`, {
      method: 'POST',
      headers: { 'X-Session-Token': sessionToken },
      body: JSON.stringify({ state_version: stateVersion }),
    });
  },

  // Operator endpoints
  async createSession(
    payload: {
      mode?: string;
      environment_order?: string[];
      participant_id?: string;
      protocol_id?: string;
    },
    operatorToken: string
  ): Promise<{ session: SessionInfo; trial_count: number; first_trial_id: string }> {
    return request('/api/operator/sessions', {
      method: 'POST',
      headers: { 'X-Operator-Token': operatorToken },
      body: JSON.stringify(payload),
    });
  },

  async listSessions(operatorToken: string): Promise<SessionInfo[]> {
    return request<SessionInfo[]>('/api/operator/sessions', {
      method: 'GET',
      headers: { 'X-Operator-Token': operatorToken },
    });
  },

  async getSessionDetail(
    sessionId: string,
    operatorToken: string
  ): Promise<{
    session: SessionInfo;
    trials: Array<Record<string, any>>;
    events: EventRecord[];
    event_count: number;
  }> {
    return request(`/api/operator/sessions/${sessionId}`, {
      method: 'GET',
      headers: { 'X-Operator-Token': operatorToken },
    });
  },

  getExportZipUrl(sessionId: string): string {
    return `/api/operator/sessions/${sessionId}/export`;
  },
};
