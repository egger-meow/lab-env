export type EnvironmentId = 'puzzle_hints' | 'bret_discrete';

export type TrialStatus =
  | 'created'
  | 'active'
  | 'decision_open'
  | 'decision_committed'
  | 'executing'
  | 'paused'
  | 'completed'
  | 'completed_without_decision'
  | 'skipped'
  | 'aborted';

export interface ActionSpec {
  action_id: string;
  label?: string;
  name?: string;
  description: string;
  category?: string;
  k?: number;
}

export interface Clue {
  clue_id: string;
  clue_type: string;
  source_text: string;
  item_a?: string;
  item_b?: string;
  item?: string;
  position?: number;
}

export interface PuzzlePublicStimulus {
  num_positions: number;
  items: string[];
  clues: Clue[];
}

export interface BretOption {
  action_id: string;
  k: number;
  description: string;
}

export interface BretPublicStimulus {
  num_boxes: number;
  reward_per_box: number;
  options: BretOption[];
}

export interface ParticipantTrialView {
  trial_id: string;
  session_id: string;
  environment_id: EnvironmentId;
  item_id: string;
  collection_index: number;
  status: TrialStatus;
  state_version: number;
  public_state: Record<string, any>;
  active_play_ms: number;
  display_order: string[];
  public_stimulus: PuzzlePublicStimulus | BretPublicStimulus | any;
  action_specs: ActionSpec[];
  language: string;
  template_id?: string;
}

export interface SessionInfo {
  session_id: string;
  participant_id: string;
  session_code: string;
  mode: string;
  protocol_id: string;
  protocol_version: string;
  environment_order: EnvironmentId[];
  status: string;
  created_at: string;
  completed_at?: string;
}

export interface JoinSessionResponse {
  session: SessionInfo;
  session_token: string;
  current_trial_id: string | null;
  session_completed: boolean;
  total_trials: number;
}

export interface DecisionRecordResponse {
  decision_id: string;
  trial_id: string;
  decision_index: number;
  acceptable_by_action: Record<string, string>;
  selected_action_id: string;
  preferred_action_ids?: string[];
  reason?: string;
  selection_acceptability_override: boolean;
  deliberation_ms: number;
  source: string;
}

export interface OutcomeResponse {
  outcome_id: string;
  trial_id: string;
  action_id: string;
  executed_payload: Record<string, any>;
  result_summary: Record<string, any>;
  completed_at: string;
}

export interface CommitDecisionResponse {
  idempotent: boolean;
  decision: DecisionRecordResponse;
  trial_status?: TrialStatus;
  state_version?: number;
  public_state?: Record<string, any>;
  outcome?: OutcomeResponse;
}

export interface EventRecord {
  event_id: string;
  session_id: string;
  trial_id: string;
  sequence_no: number;
  timestamp_utc: string;
  event_type: string;
  payload: Record<string, any>;
  state_version_before: number;
  state_version_after: number;
}
