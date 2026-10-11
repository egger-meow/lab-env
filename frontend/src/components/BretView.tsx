import { useDraftState } from '../useDraftState';
import React, { useState, useRef } from 'react';
import {
  Bomb,
  Coins,
  ShieldCheck,
  AlertTriangle,
  ArrowRight,
  Sparkles,
} from 'lucide-react';
import type { ParticipantTrialView, BretOption } from '../types';
import { api, ApiError } from '../api/client';

interface BretViewProps {
  trial: ParticipantTrialView;
  sessionToken: string;
  onTrialUpdated: (updated: ParticipantTrialView) => void;
  onNextTrial: () => Promise<void>;
  onPause: (activePlayMs: number) => Promise<void>;
  onSkip: (activePlayMs: number) => Promise<void>;
  hasNext: boolean;
}

export const BretView: React.FC<BretViewProps> = ({
  trial,
  sessionToken,
  onTrialUpdated,
  onNextTrial,
  onSkip,
  onPause,
  hasNext,
}) => {
  const stimulus = trial.public_stimulus;
  const numBoxes = stimulus?.num_boxes || 100;
  const rewardPerBox = stimulus?.reward_per_box || 1;
  const options: BretOption[] = [...(stimulus?.options || [])].sort((a, b) => trial.display_order.indexOf(a.action_id) - trial.display_order.indexOf(b.action_id));
  const isTutorial = Boolean(trial.public_state.is_tutorial);
  const tutorialType = trial.public_state.tutorial_type;

  // Decision form state for regular trial
  const [acceptableMap, setAcceptableMap] = useDraftState<Record<string, string>>( trial.trial_id, 'acceptableMap', {});
  const [selectedActionId, setSelectedActionId] = useDraftState<string | null>( trial.trial_id, 'selectedActionId', null);
  const [reason, setReason] = useDraftState<string>( trial.trial_id, 'reason', '');
  const [overrideConfirmed, setOverrideConfirmed] = useDraftState<boolean>( trial.trial_id, 'overrideConfirmed', false);
  const [loadingAction, setLoadingAction] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Comprehension state
  const [quizAnswers, setQuizAnswers] = useDraftState<Record<string, string>>( trial.trial_id, 'quizAnswers', {});
  const [comprehensionFeedback, setComprehensionFeedback] = useState<any[] | null>(
    trial.public_state.comprehension_feedback || null
  );

  const [startedAt] = useDraftState<number>(trial.trial_id, 'startedAt', Date.now());
  const startTimeRef = useRef<number>(startedAt);
  const idempotencyKeyRef = useRef<string>(`bret_${trial.trial_id}_v${trial.state_version}_${Date.now()}`);

  const openingRef = useRef(false);
  React.useEffect(() => {
    if (!openingRef.current && !isTutorial && trial.status === 'active') {
      openingRef.current = true;
      setLoadingAction('open');
      api.openDecision(trial.trial_id, trial.active_play_ms, trial.state_version, sessionToken)
        .then(() => api.getTrial(trial.trial_id, sessionToken)).then(onTrialUpdated)
        .catch(err => setErrorMessage(err.message)).finally(() => { openingRef.current = false; setLoadingAction(null); });
    }
  }, [trial.trial_id, trial.status]);

  React.useEffect(() => {
    const pause = () => {
      if (trial.status === 'active' || trial.status === 'decision_open') void onPause(trial.active_play_ms);
    };
    const visibility = () => { if (document.hidden) pause(); };
    window.addEventListener('blur', pause);
    document.addEventListener('visibilitychange', visibility);
    return () => { window.removeEventListener('blur', pause); document.removeEventListener('visibilitychange', visibility); };
  }, [trial.status, trial.state_version, onPause, trial.active_play_ms]);

  const isCompleted = trial.status === 'completed' || trial.status === 'skipped' || trial.status === 'aborted';
  const bombRevealed = Boolean(trial.public_state.bomb_revealed);
  const bombIndex = trial.public_state.bomb_index;
  const isHit = trial.public_state.is_hit;
  const payoff = trial.public_state.payoff;
  const selectedK = trial.public_state.selected_k ?? null;

  // Handle Demonstration step
  const handleStepDemo = async (stepIdx: number) => {
    setLoadingAction('demo');
    setErrorMessage(null);
    try {
      const res = await api.stepDemonstration(
        trial.trial_id,
        stepIdx,
        trial.state_version,
        sessionToken
      );
      onTrialUpdated({
        ...trial,
        status: res.status as any,
        state_version: res.state_version,
        public_state: res.public_state,
      });
    } catch (err: any) {
      setErrorMessage(err.message || '步進展示失敗');
    } finally {
      setLoadingAction(null);
    }
  };

  // Handle Comprehension submit
  const handleComprehensionSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoadingAction('comprehension');
    setErrorMessage(null);
    const deliberationMs = Math.max(0, Date.now() - startTimeRef.current);
    try {
      const res = await api.submitComprehension(
        trial.trial_id,
        quizAnswers,
        deliberationMs,
        trial.state_version,
        sessionToken
      );
      setComprehensionFeedback(res.feedback);
      onTrialUpdated({
        ...trial,
        status: res.status as any,
        state_version: res.state_version,
        public_state: res.public_state,
      });
    } catch (err: any) {
      setErrorMessage(err.message || '提交理解確認失敗');
    } finally {
      setLoadingAction(null);
    }
  };

  // Handle Decision submit for regular BRET
  const handleDecisionSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);

    for (const opt of options) {
      if (!acceptableMap[opt.action_id]) {
        setErrorMessage(`請對所有方案標記是否可接受（尚未評估取 ${opt.k} 箱方案）`);
        return;
      }
    }

    if (!selectedActionId) {
      setErrorMessage('請選擇本輪實際要執行的取箱方案');
      return;
    }

    const isMarkedNo = acceptableMap[selectedActionId] === 'no';
    if (isMarkedNo && !overrideConfirmed) {
      setErrorMessage('您選擇了標記為不可接受的方案，請勾選確認方可提交');
      return;
    }

    setLoadingAction('commit');
    const deliberationMs = Math.max(0, Date.now() - startTimeRef.current);
    try {
      const res = await api.commitDecision(
        trial.trial_id,
        {
          idempotency_key: idempotencyKeyRef.current,
          acceptable_by_action: acceptableMap,
          selected_action_id: selectedActionId,

          deliberation_ms: deliberationMs,
          state_version: trial.state_version,
          reason: reason.trim() ? reason.trim() : undefined,
          selection_acceptability_override: isMarkedNo,
        },
        sessionToken
      );

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
        setErrorMessage('版本衝突，已為您同步最新資料，請重試');
      } else {
        setErrorMessage(err.message || '提交決策失敗');
      }
    } finally {
      setLoadingAction(null);
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Header Controls */}
      <div className="bg-white rounded-2xl border border-slate-200 p-4 md:p-5 flex flex-wrap items-center justify-between gap-4 shadow-xs">
        <div className="flex items-center space-x-3">
          <div className="w-9 h-9 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center font-bold text-sm border border-indigo-100">
            #{trial.collection_index + 1}
          </div>
          <div>
            <h2 className="text-base font-bold text-slate-900 leading-tight">
              離散取箱風險決策 (BRET Discrete)
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              題號: <span className="font-mono">{trial.item_id}</span>
              {isTutorial ? (
                <span className="ml-2 px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 text-[10px] font-bold">
                  教學說明題
                </span>
              ) : (
                <span className="ml-2 px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 text-[10px] font-bold">
                  先導回合
                </span>
              )}
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-2">
          <span className="text-[11px] text-slate-400 italic">
            本實驗為無現金兌換之研究點數
          </span>
          {!isCompleted && (
            <button
              type="button"
              onClick={() => onSkip(trial.active_play_ms)}
              className="px-3 py-1.5 rounded-xl border border-slate-200 bg-white hover:bg-rose-50 hover:text-rose-700 text-slate-600 text-xs font-semibold shadow-2xs transition-all"
            >
              跳過此題
            </button>
          )}
        </div>
      </div>

      {errorMessage && (
        <div className="p-3.5 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 text-xs flex items-start space-x-2">
          <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
          <div className="font-medium">{errorMessage}</div>
        </div>
      )}

      {/* TUTORIAL: Demonstration Branch */}
      {isTutorial && tutorialType === 'demonstration' && (
        <div className="bg-white rounded-2xl border border-slate-200 p-6 md:p-8 space-y-6 shadow-xs">
          <div className="border-b border-slate-100 pb-4">
            <span className="text-xs font-bold uppercase tracking-wider text-amber-600 block mb-1">
              教學示範：機制原理展示
            </span>
            <h3 className="text-xl font-bold text-slate-900">
              固定示範（非隨機抽樣，不計點數）
            </h3>
            <p className="text-xs text-slate-500 mt-1 leading-relaxed">
              在此展示中，您將看見取箱後可能發生的兩種情況：安全未命中（獲得點數）與命中炸彈（本輪點數歸零）。
            </p>
          </div>

          <div className="space-y-4">
            {(trial.public_state.fixed_demonstrations || []).map((step: any, idx: number) => {
              const currentIdx = trial.public_state.current_demonstration_index || 0;
              const isRevealed = idx < currentIdx;
              const isCurrent = idx === currentIdx;

              return (
                <div
                  key={idx}
                  className={`p-4 rounded-xl border transition-all ${
                    isRevealed
                      ? 'bg-slate-50 border-slate-200'
                      : isCurrent
                      ? 'bg-indigo-50/50 border-indigo-200 ring-2 ring-indigo-500/10'
                      : 'bg-white border-slate-100 opacity-60'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div>
                      <span className="text-xs font-bold text-slate-800 block">
                        展示步驟 {idx + 1}: {step.label}
                      </span>
                      <p className="text-xs text-slate-600 mt-1">{isRevealed ? step.explanation : '請執行此步驟查看示範結果。'}</p>
                    </div>

                    {isRevealed && (
                      <span className="text-xs px-2.5 py-1 rounded bg-emerald-100 text-emerald-800 font-semibold shrink-0">
                        已完成
                      </span>
                    )}

                    {isCurrent && !isCompleted && (
                      <button
                        type="button"
                        onClick={() => handleStepDemo(idx)}
                        disabled={loadingAction === 'demo'}
                        className="py-1.5 px-4 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-semibold shadow-xs shrink-0"
                      >
                        {loadingAction === 'demo' ? '展示中...' : '執行此展示步驟'}
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          {isCompleted && (
            <div className="pt-4 border-t border-slate-100 flex justify-end">
              <button
                type="button"
                onClick={onNextTrial}
                className="py-3 px-6 bg-sky-600 hover:bg-sky-700 text-white font-semibold rounded-xl shadow-md shadow-sky-200 transition-all flex items-center space-x-2"
              >
                <span>{hasNext ? '進入下一題' : '完成試驗'}</span>
                <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          )}
        </div>
      )}

      {/* TUTORIAL: Comprehension Branch */}
      {isTutorial && tutorialType === 'comprehension' && (
        <div className="bg-white rounded-2xl border border-slate-200 p-6 md:p-8 space-y-6 shadow-xs">
          <div className="border-b border-slate-100 pb-4">
            <span className="text-xs font-bold uppercase tracking-wider text-amber-600 block mb-1">
              教學理解確認
            </span>
            <h3 className="text-xl font-bold text-slate-900">
              規則理解確認題目
            </h3>
            <p className="text-xs text-slate-500 mt-1 leading-relaxed">
              請回答以下簡短題目以確認您已完全理解取箱規則（答錯可重看說明，不做智力評估）。
            </p>
          </div>

          <form onSubmit={handleComprehensionSubmit} className="space-y-6">
            {(trial.public_state.comprehension_check?.questions || []).map((q: any) => {
              const currentAns = quizAnswers[q.question_id];
              const fb = comprehensionFeedback?.find((f) => f.question_id === q.question_id);

              return (
                <div
                  key={q.question_id}
                  className="p-5 rounded-xl border border-slate-200 bg-slate-50/60 space-y-3"
                >
                  <h4 className="text-sm font-bold text-slate-900">{q.prompt}</h4>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    {q.options.map((opt: string) => (
                      <label
                        key={opt}
                        className={`p-3 rounded-lg border text-xs font-semibold cursor-pointer transition-all flex items-center space-x-2.5 ${
                          currentAns === opt
                            ? 'bg-sky-50 border-sky-500 text-sky-900 shadow-xs'
                            : 'bg-white border-slate-200 text-slate-700 hover:border-slate-300'
                        }`}
                      >
                        <input
                          type="radio"
                          name={q.question_id}
                          value={opt}
                          disabled={isCompleted}
                          checked={currentAns === opt}
                          onChange={() =>
                            setQuizAnswers((prev) => ({ ...prev, [q.question_id]: opt }))
                          }
                          className="h-4 w-4 text-sky-600 focus:ring-sky-500"
                        />
                        <span>{opt}</span>
                      </label>
                    ))}
                  </div>

                  {fb && (
                    <div
                      className={`p-3 rounded-lg text-xs leading-relaxed ${
                        fb.correct
                          ? 'bg-emerald-50 text-emerald-800 border border-emerald-200'
                          : 'bg-rose-50 text-rose-800 border border-rose-200'
                      }`}
                    >
                      <span className="font-bold">{fb.correct ? '正確！' : '不正確：'}</span>{' '}
                      {fb.explanation}
                    </div>
                  )}
                </div>
              );
            })}

            {!isCompleted && (
              <div className="flex justify-end">
                <button
                  type="submit"
                  disabled={loadingAction === 'comprehension'}
                  className="py-3 px-6 bg-sky-600 hover:bg-sky-700 text-white font-semibold rounded-xl shadow-md shadow-sky-200 transition-all"
                >
                  {loadingAction === 'comprehension' ? '驗證中...' : '送出理解回答'}
                </button>
              </div>
            )}
          </form>

          {isCompleted && (
            <div className="pt-4 border-t border-slate-100 flex justify-end">
              <button
                type="button"
                onClick={onNextTrial}
                className="py-3 px-6 bg-sky-600 hover:bg-sky-700 text-white font-semibold rounded-xl shadow-md shadow-sky-200 transition-all flex items-center space-x-2"
              >
                <span>{hasNext ? '前進先導題目' : '完成試驗'}</span>
                <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          )}
        </div>
      )}

      {/* REGULAR PILOT / FORMAL TASK BRANCH */}
      {!isTutorial && (
        <div className="bg-white rounded-2xl border border-slate-200 p-6 md:p-8 space-y-6 shadow-xs">
          {/* Rules Summary Card */}
          <div className="bg-slate-50 rounded-xl p-4 border border-slate-200 text-xs text-slate-600 flex flex-wrap items-center justify-between gap-4">
            <div>
              <span className="font-bold text-slate-800">總箱數：</span>
              <span className="font-mono font-bold text-slate-900 mr-4">{numBoxes} 箱</span>
              <span className="font-bold text-slate-800">每箱點數：</span>
              <span className="font-mono font-bold text-slate-900 mr-4">{rewardPerBox} 點</span>
              <span className="font-bold text-slate-800">炸彈數量：</span>
              <span className="text-slate-900">恰有 1 個（均勻隨機藏於 1..{numBoxes}）</span>
            </div>
          </div>

          {/* Boxes Grid Visualization */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-bold text-slate-700 uppercase tracking-wider">
                箱子比例展示圖（共 {numBoxes} 個箱子）
              </span>
              {selectedK !== null && (
                <span className="text-xs font-semibold text-slate-600">
                  您收集了前 <span className="font-bold text-indigo-600">{selectedK}</span> 箱
                </span>
              )}
            </div>

            <div
              className="grid gap-1 bg-slate-100 p-3 rounded-2xl border border-slate-200 overflow-hidden"
              style={{
                gridTemplateColumns: numBoxes > 20 ? 'repeat(10, minmax(0, 1fr))' : 'repeat(10, minmax(0, 1fr))',
              }}
            >
              {Array.from({ length: numBoxes }, (_, i) => {
                const boxNum = i + 1;
                const isCollected = selectedK !== null && boxNum <= selectedK;
                const isBomb = bombRevealed && boxNum === bombIndex;

                return (
                  <div
                    key={boxNum}
                    className={`h-7 md:h-8 rounded-lg flex items-center justify-center text-[10px] font-mono font-bold transition-all ${
                      isBomb
                        ? 'bg-rose-500 text-white ring-2 ring-rose-400'
                        : isCollected
                        ? 'bg-indigo-600 text-white shadow-xs'
                        : 'bg-white text-slate-400 border border-slate-200/60'
                    }`}
                  >
                    {isBomb ? <Bomb className="w-3.5 h-3.5 fill-white" /> : boxNum}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Outcome revelation card */}
          {bombRevealed && (
            <div
              className={`p-6 rounded-2xl border text-center space-y-2 ${
                isHit
                  ? 'bg-rose-50 border-rose-200 text-rose-950'
                  : 'bg-emerald-50 border-emerald-200 text-emerald-950'
              }`}
            >
              <div
                className={`w-12 h-12 rounded-2xl mx-auto flex items-center justify-center ${
                  isHit ? 'bg-rose-100 text-rose-600' : 'bg-emerald-100 text-emerald-600'
                }`}
              >
                {isHit ? <Bomb className="w-6 h-6" /> : <ShieldCheck className="w-6 h-6" />}
              </div>
              <h3 className="text-xl font-bold tracking-tight">
                {isHit ? '命中炸彈' : '未命中炸彈'}
              </h3>
              <p className="text-xs leading-relaxed max-w-md mx-auto text-slate-600">
                炸彈位於第 <span className="font-bold text-slate-900">{bombIndex}</span> 箱。您選擇收集了前{' '}
                <span className="font-bold text-slate-900">{selectedK}</span> 箱。
                {isHit
                  ? ' 炸彈在您收集的範圍內，本輪收益為 0 點。'
                  : ` 炸彈在您收集範圍之外，本輪點數為 ${payoff} 點。`}
              </p>
              <div className="pt-2">
                <span className="inline-flex items-center space-x-1.5 px-4 py-1.5 rounded-full bg-white border font-bold text-sm shadow-xs">
                  <Coins className="w-4 h-4 text-amber-500" />
                  <span>本輪結算：{payoff} 點</span>
                </span>
              </div>
            </div>
          )}

          {/* Action Cards Selection (if not yet committed) */}
          {!bombRevealed && !isCompleted && (
            <form onSubmit={handleDecisionSubmit} className="space-y-4 pt-2">
              <h3 className="text-xs font-bold text-slate-700 uppercase tracking-wider">
                請在下方 4 項方案中表達可接受性，並指定執行方案：
              </h3>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {options.map((opt) => {
                  const isSelected = selectedActionId === opt.action_id;
                  const currentRating = acceptableMap[opt.action_id];
                  const hitProb = Math.round((opt.k / numBoxes) * 100);
                  const safeProb = 100 - hitProb;
                  const safePayoff = opt.k * rewardPerBox;

                  return (
                    <div
                      key={opt.action_id}
                      className={`p-4 rounded-xl border transition-all ${
                        isSelected
                          ? 'border-indigo-500 bg-indigo-50/40 ring-2 ring-indigo-500/20 shadow-sm'
                          : 'border-slate-200 bg-white hover:border-slate-300'
                      }`}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <label className="flex items-start space-x-3 cursor-pointer select-none grow">
                          <input
                            type="radio"
                            name="selected_bret_action"
                            value={opt.action_id}
                            checked={isSelected}
                            onChange={() => {
                              setSelectedActionId(opt.action_id);
                              if (acceptableMap[opt.action_id] !== 'no') {
                                setOverrideConfirmed(false);
                              }
                            }}
                            className="mt-1 h-4 w-4 text-indigo-600 focus:ring-indigo-500"
                          />
                          <div>
                            <span className="text-base font-bold text-slate-900 block">
                              收集前 {opt.k} 箱
                            </span>
                            <div className="text-xs text-slate-500 space-y-0.5 mt-1">
                              <p>• 沒取到炸彈 ({safeProb}%)：獲得 <strong className="text-slate-800">{safePayoff} 點</strong></p>
                              <p>• 取到炸彈 ({hitProb}%)：獲得 <strong className="text-slate-800">0 點</strong></p>
                            </div>
                          </div>
                        </label>

                        {/* Acceptability evaluation */}
                        <div className="shrink-0 flex items-center space-x-1 bg-slate-100 p-1 rounded-lg border border-slate-200/80">
                          {(['yes', 'no', 'unsure'] as const).map((val) => (
                            <button
                              key={val}
                              aria-pressed={currentRating === val}
                              type="button"
                              onClick={() =>
                                setAcceptableMap((prev) => ({ ...prev, [opt.action_id]: val }))
                              }
                              className={`px-2 py-1 text-xs font-semibold rounded-md transition-all ${
                                currentRating === val
                                  ? val === 'yes'
                                    ? 'bg-emerald-600 text-white'
                                    : val === 'no'
                                    ? 'bg-rose-600 text-white'
                                    : 'bg-slate-700 text-white'
                                  : 'text-slate-600 hover:text-slate-900'
                              }`}
                            >
                              {val === 'yes' ? '可接受' : val === 'no' ? '不可' : '說不準'}
                            </button>
                          ))}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>

              {selectedActionId && acceptableMap[selectedActionId] === 'no' && (
                <div className="p-3.5 bg-amber-50 border border-amber-200 rounded-xl text-xs text-amber-900 space-y-1.5">
                  <span className="font-semibold block">中性確認提醒：</span>
                  <p className="text-slate-600">
                    您將該方案評估為「不可接受」，但同時選為實際執行的方案。若確認執行，請勾選確認方塊：
                  </p>
                  <label className="flex items-center space-x-2 pt-1 cursor-pointer font-medium text-slate-800">
                    <input
                      type="checkbox"
                      checked={overrideConfirmed}
                      onChange={(e) => setOverrideConfirmed(e.target.checked)}
                      className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                    />
                    <span>我確認執行此方案</span>
                  </label>
                </div>
              )}

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  簡短決策理由說明（選填）：
                </label>
                <textarea
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="說明您做此選擇的考量..."
                  rows={2}
                  className="w-full text-xs rounded-xl border-slate-200 p-2.5 focus:ring-indigo-500 focus:border-indigo-500"
                />
              </div>

              <div className="flex justify-end pt-2">
                <button
                  type="submit"
                  disabled={loadingAction !== null || trial.status !== 'decision_open'}
                  className="py-3 px-6 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold rounded-xl shadow-md shadow-indigo-200 transition-all flex items-center space-x-2 disabled:opacity-50"
                >
                  {loadingAction === 'commit' ? (
                    <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  ) : (
                    <>
                      <Sparkles className="w-4 h-4" />
                      <span>確認並執行此方案</span>
                    </>
                  )}
                </button>
              </div>
            </form>
          )}

          {/* Advance button after revelation */}
          {isCompleted && (
            <div className="pt-4 border-t border-slate-100 flex justify-end">
              <button
                type="button"
                onClick={onNextTrial}
                className="py-3 px-6 bg-sky-600 hover:bg-sky-700 text-white font-semibold rounded-xl shadow-md shadow-sky-200 transition-all flex items-center space-x-2"
              >
                <span>{hasNext ? '前進下一回合' : '完成全部試驗'}</span>
                <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
