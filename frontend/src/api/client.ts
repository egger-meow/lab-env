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

async function rawRequest<T>(url: string, options: RequestInit = {}): Promise<T> {
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

// Only operations already queued in this client may advance a captured version.
// Never replace a caller's version with an arbitrary server read.
type QueuedMutation = { inputVersion?: number; resultVersion?: number; promise: Promise<unknown> };
const queues = new Map<string, QueuedMutation[]>();
function request<T>(url: string, options: RequestInit = {}): Promise<T> {
  const match = url.match(/^\/api\/trials\/([^/]+)\/([^/]+)$/);
  if (!match || options.method !== 'POST') return rawRequest<T>(url, options);
  const [, id, operation] = match;
  const predecessors = [...(queues.get(id) || [])];
  const body = JSON.parse(options.body as string);
  const entry: QueuedMutation = { inputVersion: body.state_version, promise: Promise.resolve() };
  const task = (async () => {
    let version = body.state_version;
    for (const previous of predecessors) {
      // A failed/uncertain predecessor cannot authorize rebasing a later command.
      await previous.promise;
      if (operation !== 'decision' && previous.inputVersion === version && previous.resultVersion !== undefined) {
        version = previous.resultVersion;
      }
    }
    entry.inputVersion = version;
    if (version !== undefined) body.state_version = version;
    try {
      const result = await rawRequest<T>(url, { ...options, body: JSON.stringify(body) });
      entry.resultVersion = (result as { state_version?: number }).state_version;
      return result;
    } catch (err) {
      if (err instanceof ApiError && err.isStateVersionConflict && typeof window !== 'undefined') {
        const fresh = await rawRequest<ParticipantTrialView>(`/api/trials/${id}`, { headers: options.headers });
        window.dispatchEvent(new CustomEvent('preference-lab-conflict', { detail: fresh }));
      }
      throw err;
    }
  })();
  entry.promise = task;
  queues.set(id, [...predecessors, entry]);
  void task.finally(() => {
    const remaining = (queues.get(id) || []).filter(item => item !== entry);
    if (remaining.length) queues.set(id, remaining); else queues.delete(id);
  }).catch(() => {});
  return task;
}

// The API client is also used by Node-based local verification scripts.
const pendingStorage = typeof localStorage === 'undefined' ? {
  getItem: (_key: string): string | null => null,
  setItem: (_key: string, _value: string) => {},
  removeItem: (_key: string) => {},
} : localStorage;

export type DecisionPayload = Parameters<typeof api.commitDecision>[1];
export function notifyPendingChanged() {
  if (typeof window !== 'undefined') window.dispatchEvent(new Event('preference-lab-pending'));
}
export const pendingKey = (id: string) => `preference_lab_pending_${id}`;

// Browser blur and visibilitychange commonly fire together.
const pendingPauses = new Map<string, Promise<{ status: string; state_version: number }>>();
const settledPauseStatuses = new Set(['paused', 'skipped', 'completed', 'completed_without_decision', 'aborted']);

export const api = {
  async checkpoint(trialId: string, activePlayMs: number, stateVersion: number, sessionToken: string) {
    return request<Pick<ParticipantTrialView, 'status' | 'state_version' | 'public_state' | 'active_play_ms'>>(
      `/api/trials/${trialId}/checkpoint`, { method: 'POST', headers: { 'X-Session-Token': sessionToken },
        body: JSON.stringify({ active_play_ms: activePlayMs, state_version: stateVersion }) });
  },
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
    const key = pendingKey(trialId);
    const saved = pendingStorage.getItem(key);
    const frozen = saved ? JSON.parse(saved) : payload;
    pendingStorage.setItem(key, JSON.stringify(frozen));
    notifyPendingChanged();
    let result: CommitDecisionResponse;
    try { result = await request<CommitDecisionResponse>(`/api/trials/${trialId}/decision`, {
      method: 'POST',
      headers: { 'X-Session-Token': sessionToken },
      body: JSON.stringify(frozen),
    }); } catch (err) {
      // A version rejection is definitive: nothing was committed. A subsequent
      // confirmation is a new request; transport failures keep the frozen request.
      if (err instanceof ApiError && err.isStateVersionConflict) {
        pendingStorage.removeItem(key);
        notifyPendingChanged();
      }
      throw err;
    }
    pendingStorage.removeItem(key);
    notifyPendingChanged();
    return result;
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
    const key = JSON.stringify([trialId, sessionToken]);
    const pending = pendingPauses.get(key);
    if (pending) return pending;
    const task = (async () => {
      try {
        return await request<{ status: string; state_version: number }>(`/api/trials/${trialId}/pause`, {
          method: 'POST',
          headers: { 'X-Session-Token': sessionToken },
          body: JSON.stringify({ active_play_ms: activePlayMs, state_version: stateVersion }),
        });
      } catch (err) {
        // A skip, completion, or earlier pause may have won the race.
        // Read authoritative state without retrying or changing the trial.
        if (err instanceof ApiError && err.status === 400 && err.detail.startsWith('Cannot pause trial in status')) {
          const fresh = await api.getTrial(trialId, sessionToken);
          if (settledPauseStatuses.has(fresh.status)) {
            return { status: fresh.status, state_version: fresh.state_version };
          }
        }
        throw err;
      }
    })();
    pendingPauses.set(key, task);
    try { return await task; }
    finally { if (pendingPauses.get(key) === task) pendingPauses.delete(key); }
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
