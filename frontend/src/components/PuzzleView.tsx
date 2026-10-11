import React, { useState, useEffect, useRef } from 'react';
import {
  CheckCircle,
  RotateCcw,
  Sparkles,
  Clock,
  Lightbulb,
  AlertCircle,
  CheckCircle2,
} from 'lucide-react';
import type { ParticipantTrialView } from '../types';
import { DecisionModal } from './DecisionModal';
import { FeedbackFollowup } from './FeedbackFollowup';
import { api, ApiError } from '../api/client';

interface PuzzleViewProps {
  trial: ParticipantTrialView;
  sessionToken: string;
  onTrialUpdated: (updated: ParticipantTrialView) => void;
  onNextTrial: () => Promise<void>;
  onPause: (activePlayMs: number) => Promise<void>;
  onSkip: (activePlayMs: number) => Promise<void>;
  hasNext: boolean;
}

export const PuzzleView: React.FC<PuzzleViewProps> = ({
  trial,
  sessionToken,
  onTrialUpdated,
  onNextTrial,
  onPause,
  onSkip,
  hasNext,
}) => {
  const stimulus = trial.public_stimulus;
  const orderedSpecs = [...trial.action_specs].sort((a, b) => trial.display_order.indexOf(a.action_id) - trial.display_order.indexOf(b.action_id));
  const itemIcons: Record<string, string> = { moon: '☾', key: '⚿', gem: '◆', crown: '♛', sword: '⚔', shield: '⛨', star: '★', sun: '☀', heart: '♥', tree: '♠', circle: '●', square: '■', triangle: '▲' };
  const itemLabel = (id: string) => `${itemIcons[id] || '◇'} ${stimulus.item_labels?.[id] || id}`;
  const timeKey = `preference_lab_time_${trial.trial_id}`;
  const numPositions = stimulus?.num_positions || 4;
  const items: string[] = stimulus?.items || [];
  const clues: any[] = stimulus?.clues || [];

  const [board, setBoard] = useState<(string | null)[]>(
    trial.public_state.board || Array(numPositions).fill(null)
  );
  const [selectedInventoryItem, setSelectedInventoryItem] = useState<string | null>(null);
  const [activePlayMs, setActivePlayMs] = useState<number>(Math.max(trial.active_play_ms || 0, Number(localStorage.getItem(timeKey) || 0)));
  const [statusMessage, setStatusMessage] = useState<string | null>(
    trial.public_state.status_message || null
  );
  const [isSolved, setIsSolved] = useState<boolean>(trial.public_state.is_solved || false);
  const [attempts, setAttempts] = useState<number>(trial.public_state.attempts || 0);
  const [loadingAction, setLoadingAction] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [followupSolution, setFollowupSolution] = useState<string[] | null>(
    trial.public_state.solution_revealed_followup || null
  );

  const isRunningRef = useRef<boolean>(true);
  const playMsRef = useRef<number>(trial.active_play_ms || 0);
  playMsRef.current = activePlayMs;

  const isTerminal =
    trial.status === 'completed' ||
    trial.status === 'completed_without_decision' ||
    trial.status === 'skipped' ||
    trial.status === 'aborted';

  // Synchronize with external trial changes
  useEffect(() => {
    setBoard(trial.public_state.board || Array(numPositions).fill(null));
    setActivePlayMs((prev) => trial.status === 'active' ? Math.max(prev, trial.active_play_ms || 0) : trial.active_play_ms);
    if (trial.status !== 'active') localStorage.setItem(timeKey, String(trial.active_play_ms));
    setStatusMessage(trial.public_state.status_message || null);
    setIsSolved(trial.public_state.is_solved || false);
    setAttempts(trial.public_state.attempts || 0);
    setFollowupSolution(trial.public_state.solution_revealed_followup || null);
  }, [trial]);

  const trialRef = useRef(trial);
  trialRef.current = trial;
  const busyRef = useRef(false);
  const pauseRef = useRef(onPause);
  pauseRef.current = onPause;
  useEffect(() => {
    isRunningRef.current = trial.status === 'active' && !document.hidden;
    const pause = () => {
      isRunningRef.current = false;
      const current = trialRef.current;
      if (current.status === 'active' || current.status === 'decision_open') {
        void pauseRef.current(current.status === 'active' ? playMsRef.current : current.active_play_ms);
      }
    };
    const visibility = () => { if (document.hidden) pause(); };
    window.addEventListener('blur', pause);
    document.addEventListener('visibilitychange', visibility);
    const interval = window.setInterval(() => {
      if (!isRunningRef.current) return;
      const next = playMsRef.current + 200;
      playMsRef.current = next;
      localStorage.setItem(timeKey, String(next));
      setActivePlayMs(next);
    }, 200);
    return () => {
      clearInterval(interval);
      window.removeEventListener('blur', pause);
      document.removeEventListener('visibilitychange', visibility);
    };
  }, [trial.status, timeKey]);

  // Persist time independently of board operations; the trial-scoped local checkpoint
  // also covers refresh between heartbeats. Decision time remains frozen.
  useEffect(() => {
    if (trial.status !== 'active' || busyRef.current || loadingAction) return;
    const start = trial.public_state.post_decision_started_ms;
    const primaryDue = !trial.public_state.primary_decision_committed && activePlayMs >= 45000;
    const followupDue = start !== undefined && activePlayMs >= start + 45000;
    if (primaryDue) {
      busyRef.current = true;
      void handleOpenDecision().finally(() => { busyRef.current = false; });
    } else if (followupDue || activePlayMs - trial.active_play_ms >= 5000) {
      busyRef.current = true;
      void api.checkpoint(trial.trial_id, activePlayMs, trial.state_version, sessionToken)
        .then(res => {
          if (res.status !== 'active') {
            localStorage.setItem(timeKey, String(res.active_play_ms));
            setActivePlayMs(res.active_play_ms);
          }
          onTrialUpdated({ ...trialRef.current, ...res });
        }).catch(err => setActionError(err.message))
        .finally(() => { busyRef.current = false; });
    }
  }, [activePlayMs, trial.status, trial.state_version, loadingAction]);

  // Save board changes to backend
  const handleBoardSlotClick = async (idx: number) => {
    if (trial.status !== 'active') return;
    setActionError(null);

    const newBoard = [...board];
    if (selectedInventoryItem) {
      // If already placed in another slot, clear old slot
      const existingIdx = newBoard.indexOf(selectedInventoryItem);
      if (existingIdx !== -1) {
        newBoard[existingIdx] = null;
      }
      newBoard[idx] = selectedInventoryItem;
      setSelectedInventoryItem(null);
    } else {
      // Clear this slot
      newBoard[idx] = null;
    }

    setBoard(newBoard);

    // Call updateBoard to save state (without checking answers or leaking correctness!)
    const currentMs = Math.max(activePlayMs, trial.active_play_ms || 0);
    try {
      const res = await api.updateBoard(
        trial.trial_id,
        newBoard,
        currentMs,
        trial.state_version,
        sessionToken
      );
      onTrialUpdated({
        ...trial,
        state_version: res.state_version,
        public_state: res.public_state,
        active_play_ms: currentMs,
      });
    } catch (err: any) {
      if (err instanceof ApiError && err.isStateVersionConflict) {
        // Refresh trial
        const fresh = await api.getTrial(trial.trial_id, sessionToken);
        onTrialUpdated(fresh);
      } else {
        setActionError(err.message || '保存棋盤失敗');
      }
    }
  };

  const handleClearBoard = async () => {
    if (trial.status !== 'active') return;
    const emptyBoard = Array(numPositions).fill(null);
    setBoard(emptyBoard);
    setSelectedInventoryItem(null);
    const currentMs = Math.max(activePlayMs, trial.active_play_ms || 0);

    try {
      const res = await api.updateBoard(
        trial.trial_id,
        emptyBoard,
        currentMs,
        trial.state_version,
        sessionToken
      );
      onTrialUpdated({
        ...trial,
        state_version: res.state_version,
        public_state: res.public_state,
        active_play_ms: currentMs,
      });
    } catch (err: any) {
      setActionError(err.message);
    }
  };

  const handleCheckAnswer = async () => {
    if (trial.status !== 'active') return;
    setLoadingAction('check');
    setActionError(null);
    const currentMs = Math.max(activePlayMs, trial.active_play_ms || 0);
    try {
      const res = await api.checkAnswer(
        trial.trial_id,
        currentMs,
        trial.state_version,
        board,
        sessionToken
      );
      setStatusMessage(res.status_message);
      setIsSolved(res.is_solved);
      setAttempts(res.attempts);
      onTrialUpdated({
        ...trial,
        status: res.status as any,
        state_version: res.state_version,
        public_state: res.public_state,
        active_play_ms: currentMs,
      });
    } catch (err: any) {
      if (err instanceof ApiError && err.isStateVersionConflict) {
        const fresh = await api.getTrial(trial.trial_id, sessionToken);
        onTrialUpdated(fresh);
      } else {
        setActionError(err.message || '檢查答案時發生錯誤');
      }
    } finally {
      setLoadingAction(null);
    }
  };

  const handleOpenDecision = async () => {
    if (trial.status !== 'active' || trial.public_state.primary_decision_committed) return;
    setLoadingAction('open_decision');
    setActionError(null);
    const currentMs = Math.max(activePlayMs, trial.active_play_ms || 0);
    try {
      const res = await api.openDecision(
        trial.trial_id,
        currentMs,
        trial.state_version,
        sessionToken
      );

      // Handle case: open-decision auto-completes the trial if already completely correct!
      if (res.status === 'completed_without_decision') {
        setIsSolved(true);
        setStatusMessage('棋盤已符合全部線索！已自動為您完成');
        onTrialUpdated({
          ...trial,
          status: 'completed_without_decision',
          state_version: res.state_version,
          public_state: res.public_state || { ...trial.public_state, is_solved: true },
          active_play_ms: currentMs,
        });
      } else {
        // Transition to decision_open
        onTrialUpdated({
          ...trial,
          status: 'decision_open',
          state_version: res.state_version,
          active_play_ms: currentMs,
        });
      }
    } catch (err: any) {
      if (err instanceof ApiError && err.isStateVersionConflict) {
        const fresh = await api.getTrial(trial.trial_id, sessionToken);
        onTrialUpdated(fresh);
      } else {
        setActionError(err.message || '開啟決策選項失敗');
      }
    } finally {
      setLoadingAction(null);
    }
  };

  const handleCommitDecision = async (payload: any) => {
    setLoadingAction('commit_decision');
    setActionError(null);
    try {
      const res = await api.commitDecision(trial.trial_id, payload, sessionToken);
      if (res.trial_status) {
        onTrialUpdated({
          ...trial,
          status: res.trial_status,
          state_version: res.state_version || trial.state_version + 1,
          public_state: res.public_state || trial.public_state,
        });
      } else {
        const fresh = await api.getTrial(trial.trial_id, sessionToken);
        onTrialUpdated(fresh);
      }
    } catch (err: any) {
      if (err instanceof ApiError && err.isStateVersionConflict) {
        const fresh = await api.getTrial(trial.trial_id, sessionToken);
        onTrialUpdated(fresh);
        setActionError('畫面狀態已同步，請重新確認並提交選擇');
      } else {
        setActionError(err.message || '提交決策失敗');
      }
    } finally {
      setLoadingAction(null);
    }
  };

  const seconds = Math.floor(activePlayMs / 1000);
  const isOver45s = seconds >= 45;

  return (
    <div className="space-y-4">
      {/* Top Header Controls */}
      <div className="bg-white rounded-2xl border border-slate-200 p-4 md:p-5 flex flex-wrap items-center justify-between gap-4 shadow-xs">
        <div className="flex items-center space-x-3">
          <div className="w-9 h-9 rounded-xl bg-sky-50 text-sky-600 flex items-center justify-center font-bold text-sm border border-sky-100">
            #{trial.collection_index + 1}
          </div>
          <div>
            <h2 className="text-base font-bold text-slate-900 leading-tight">
              邏輯位置排列謎題
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              題號: <span className="font-mono">{trial.item_id}</span>
              {trial.template_id && (
                <span className="ml-2 px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 text-[10px]">
                  {trial.template_id}
                </span>
              )}
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-3">
          {/* Active Play Timer Badge */}
          <div
            className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-xl border text-xs font-mono font-bold ${
              isOver45s
                ? 'bg-amber-50 text-amber-700 border-amber-200 ring-2 ring-amber-500/20'
                : 'bg-slate-50 text-slate-700 border-slate-200'
            }`}
          >
            <Clock className="w-3.5 h-3.5 shrink-0" />
            <span>{seconds} 秒</span>
            {isOver45s && !isTerminal && (
              <span className="text-[10px] bg-amber-200/70 text-amber-900 px-1 rounded font-sans">
                可看協助
              </span>
            )}
          </div>

          {!isTerminal && (
            <>
              <button
                type="button"
                onClick={() => onPause(Math.max(activePlayMs, trial.active_play_ms || 0))}
                className="px-3 py-1.5 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 text-xs font-semibold shadow-2xs transition-all"
              >
                暫停休息
              </button>
              <button
                type="button"
                onClick={() => onSkip(Math.max(activePlayMs, trial.active_play_ms || 0))}
                className="px-3 py-1.5 rounded-xl border border-slate-200 bg-white hover:bg-rose-50 hover:text-rose-700 text-slate-600 text-xs font-semibold shadow-2xs transition-all"
              >
                跳過此題
              </button>
            </>
          )}
        </div>
      </div>

      {actionError && (
        <div className="p-3.5 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 text-xs flex items-start space-x-2">
          <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
          <div className="font-medium">{actionError}</div>
        </div>
      )}

      {/* Revealed Hint Callout */}
      {trial.public_state.revealed_hint && (
        <div className="p-4 rounded-xl bg-amber-50 border border-amber-200 text-amber-900 text-xs flex items-start space-x-3 shadow-xs">
          <Lightbulb className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
          <div>
            <h4 className="font-bold text-amber-950 mb-0.5">方向引導提示：</h4>
            <p className="text-slate-700 leading-relaxed">
              {trial.public_state.revealed_hint}
            </p>
          </div>
        </div>
      )}

      {/* Clues Card */}
      <div className="bg-white rounded-2xl border border-slate-200 p-4 shadow-xs">
        <h3 className="text-xs font-bold text-slate-700 uppercase tracking-wider mb-3 flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-sky-500"></span>
          本題已知線索 (Clues)
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
          {clues.map((c, idx) => (
            <div
              key={c.clue_id || idx}
              className="p-3 rounded-xl bg-slate-50 border border-slate-200/80 text-xs text-slate-800 leading-relaxed font-medium flex items-start space-x-2"
            >
              <span className="w-5 h-5 rounded-full bg-white text-slate-500 flex items-center justify-center shrink-0 border border-slate-200 text-[10px] font-bold">
                {idx + 1}
              </span>
              <span>{c.text_zh || c.source_text}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Board & Inventory Section */}
      <div className="bg-white rounded-2xl border border-slate-200 p-4 md:p-5 shadow-xs space-y-4">
        <div>
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-xs font-bold text-slate-700 uppercase tracking-wider flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-sky-500"></span>
              排列棋盤 (1 到 {numPositions} 格)
            </h3>
            {statusMessage && (
              <span
                className={`text-xs px-2.5 py-1 rounded-lg font-semibold flex items-center gap-1.5 ${
                  isSolved
                    ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                    : 'bg-amber-50 text-amber-800 border border-amber-200'
                }`}
              >
                {isSolved ? <CheckCircle2 className="w-3.5 h-3.5" /> : null}
                {statusMessage}
              </span>
            )}
          </div>

          {/* Board Slots */}
          <div
            className="grid gap-3"
            style={{ gridTemplateColumns: `repeat(${numPositions}, minmax(0, 1fr))` }}
          >
            {board.map((val, idx) => {
              const isSlotFilled = val !== null;
              return (
                <button
                  key={idx}
                  type="button"
                  disabled={trial.status !== 'active' || loadingAction !== null || busyRef.current}
                  onClick={() => handleBoardSlotClick(idx)}
                  className={`h-20 rounded-2xl border-2 transition-all flex flex-col items-center justify-center p-2 relative group ${
                    isSlotFilled
                      ? 'border-sky-500 bg-sky-50/50 shadow-sm'
                      : selectedInventoryItem
                      ? 'border-dashed border-sky-400 bg-sky-50/20 hover:bg-sky-50/50'
                      : 'border-dashed border-slate-300 bg-slate-50/50 hover:border-slate-400'
                  }`}
                >
                  <span className="absolute top-2 left-2 text-[10px] font-bold text-slate-400">
                    第 {idx + 1} 格
                  </span>
                  {isSlotFilled ? (
                    <div className="text-center">
                      <span className="text-base md:text-lg font-bold text-slate-900 capitalize block tracking-tight">
                        {itemLabel(val!)}
                      </span>
                      {!isTerminal && (
                        <span className="text-[10px] text-slate-400 group-hover:text-rose-500 transition-colors block mt-1">
                          點擊移除
                        </span>
                      )}
                    </div>
                  ) : (
                    <span className="text-xs text-slate-400 font-medium">
                      {selectedInventoryItem ? '點擊放置' : '空位'}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </div>

        {/* Item Inventory Palette */}
        {!isTerminal && (
          <div className="pt-2 border-t border-slate-100">
            <div className="flex items-center justify-between mb-2.5">
              <span className="text-xs font-bold text-slate-600">
                可選擇圖案（點擊選取後放入上方格子）：
              </span>
              <button
                type="button"
                onClick={handleClearBoard}
                className="text-xs text-slate-500 hover:text-slate-800 flex items-center space-x-1"
              >
                <RotateCcw className="w-3 h-3" />
                <span>清空重排</span>
              </button>
            </div>

            <div className="flex flex-wrap gap-2.5">
              {items.map((it) => {
                const isPlaced = board.includes(it);
                const isSelected = selectedInventoryItem === it;

                return (
                  <button
                    key={itemLabel(it)}
                    type="button"
                    onClick={() =>
                      setSelectedInventoryItem((prev) => (prev === it ? null : it))
                    }
                    className={`py-2 px-4 rounded-xl text-xs font-bold capitalize transition-all border ${
                      isSelected
                        ? 'bg-sky-600 text-white border-sky-600 shadow-md shadow-sky-200 ring-2 ring-sky-500/20'
                        : isPlaced
                        ? 'bg-slate-100 text-slate-400 border-slate-200'
                        : 'bg-white text-slate-700 border-slate-200 hover:border-slate-400 shadow-2xs'
                    }`}
                  >
                    {itemLabel(it)}
                    {isPlaced && <span className="ml-1 text-[10px]">(已放)</span>}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* Bottom Actions Row */}
        {!isTerminal && (
          <div className="pt-3 border-t border-slate-100 flex flex-wrap items-center justify-between gap-3">
            <div className="text-xs text-slate-500">
              已檢查嘗試次數：<span className="font-mono font-bold text-slate-700">{attempts}</span> 次
            </div>

            <div className="flex items-center space-x-3">
              <button
                type="button"
                onClick={handleOpenDecision}
                disabled={loadingAction !== null || Boolean(trial.public_state.primary_decision_committed)}
                className={`py-2.5 px-4 rounded-xl text-xs font-semibold transition-all flex items-center space-x-1.5 border ${
                  isOver45s
                    ? 'bg-amber-500 hover:bg-amber-600 text-white border-amber-500 shadow-sm shadow-amber-200'
                    : 'bg-white hover:bg-slate-50 text-slate-700 border-slate-300'
                }`}
              >
                <Sparkles className="w-3.5 h-3.5" />
                <span>我想看看協助選項</span>
              </button>

              <button
                type="button"
                onClick={handleCheckAnswer}
                disabled={loadingAction !== null}
                className="py-2.5 px-5 bg-sky-600 hover:bg-sky-700 active:bg-sky-800 text-white rounded-xl text-xs font-semibold shadow-md shadow-sky-200 transition-all flex items-center space-x-1.5 disabled:opacity-50"
              >
                {loadingAction === 'check' ? (
                  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                ) : (
                  <>
                    <CheckCircle className="w-3.5 h-3.5" />
                    <span>檢查答案</span>
                  </>
                )}
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Terminal Feedback & Next Trial Section */}
      {isTerminal && (
        <FeedbackFollowup
          status={trial.status}
          environmentId={trial.environment_id}
          isSolved={isSolved}
          solution={followupSolution?.map(itemLabel)}
          hasFeedbackSubmitted={Boolean(trial.public_state.feedback)}
          onSubmitFeedback={async (fb) => {
            await api.submitFeedback(
              trial.trial_id,
              fb,
              trial.state_version,
              sessionToken
            );
            const fresh = await api.getTrial(trial.trial_id, sessionToken);
            onTrialUpdated(fresh);
          }}
          onRevealSolution={async () => {
            const res = await api.revealSolutionFollowup(
              trial.trial_id,
              trial.state_version,
              sessionToken
            );
            setFollowupSolution(res.solution);
            const fresh = await api.getTrial(trial.trial_id, sessionToken);
            onTrialUpdated(fresh);
          }}
          onNext={onNextTrial}
          loading={loadingAction === 'next'}
          hasNext={hasNext}
        />
      )}

      {/* Decision Modal */}
      {trial.status === 'decision_open' && (
        <DecisionModal
          trialId={trial.trial_id}
          stateVersion={trial.state_version}
          actionSpecs={orderedSpecs}
          onSkip={() => onSkip(trial.active_play_ms)}
          onSubmit={handleCommitDecision}
          loading={loadingAction === 'commit_decision'}
          error={actionError}
        />
      )}
    </div>
  );
};
