import React, { useState, useEffect, useRef } from 'react';
import { HelpCircle, AlertTriangle, Check, ShieldAlert } from 'lucide-react';
import type { ActionSpec } from '../types';

interface DecisionModalProps {
  trialId: string;
  stateVersion: number;
  actionSpecs: ActionSpec[];
  onSubmit: (payload: {
    idempotency_key: string;
    acceptable_by_action: Record<string, string>;
    selected_action_id: string;
    preferred_action_ids?: string[];
    deliberation_ms: number;
    state_version: number;
    reason?: string;
    selection_acceptability_override?: boolean;
  }) => Promise<void>;
  loading: boolean;
  error?: string | null;
}

export const DecisionModal: React.FC<DecisionModalProps> = ({
  trialId,
  stateVersion,
  actionSpecs,
  onSubmit,
  loading,
  error,
}) => {
  const [acceptableMap, setAcceptableMap] = useState<Record<string, string>>({});
  const [selectedActionId, setSelectedActionId] = useState<string | null>(null);
  const [reason, setReason] = useState<string>('');
  const [overrideConfirmed, setOverrideConfirmed] = useState<boolean>(false);
  const [validationError, setValidationError] = useState<string | null>(null);

  const startTimeRef = useRef<number>(Date.now());
  const idempotencyKeyRef = useRef<string>(`dec_${trialId}_v${stateVersion}_${Date.now()}`);

  useEffect(() => {
    startTimeRef.current = Date.now();
  }, []);

  useEffect(() => {
    idempotencyKeyRef.current = `dec_${trialId}_v${stateVersion}_${Date.now()}`;
  }, [trialId, stateVersion]);

  const handleSelectAcceptability = (actionId: string, val: 'yes' | 'no' | 'unsure') => {
    setAcceptableMap((prev) => ({ ...prev, [actionId]: val }));
    setValidationError(null);
  };

  const handleSelectAction = (actionId: string) => {
    setSelectedActionId(actionId);
    setValidationError(null);
    if (acceptableMap[actionId] !== 'no') {
      setOverrideConfirmed(false);
    }
  };

  const isSelectedActionMarkedNo = selectedActionId ? acceptableMap[selectedActionId] === 'no' : false;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setValidationError(null);

    // 1. Validate all actions have an acceptability evaluation
    for (const spec of actionSpecs) {
      if (!acceptableMap[spec.action_id]) {
        const actionTitle = spec.label || spec.name || spec.action_id;
        setValidationError(`請對所有方案標記可接受性（您尚未評估「${actionTitle}」）`);
        return;
      }
    }

    // 2. Validate an action is selected
    if (!selectedActionId) {
      setValidationError('請選擇本次實際要執行的方案');
      return;
    }

    // 3. Validate override confirmation if selected action was marked "no"
    if (isSelectedActionMarkedNo && !overrideConfirmed) {
      setValidationError('您選擇了標記為不可接受的方案，請勾選確認執行方可提交');
      return;
    }

    const deliberationMs = Math.max(0, Date.now() - startTimeRef.current);

    await onSubmit({
      idempotency_key: idempotencyKeyRef.current,
      acceptable_by_action: acceptableMap,
      selected_action_id: selectedActionId,
      preferred_action_ids: [selectedActionId],
      deliberation_ms: deliberationMs,
      state_version: stateVersion,
      reason: reason.trim() ? reason.trim() : undefined,
      selection_acceptability_override: isSelectedActionMarkedNo,
    });
  };

  return (
    <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4 overflow-y-auto">
      <div className="bg-white rounded-2xl shadow-2xl max-w-2xl w-full my-8 p-6 md:p-8 border border-slate-200 animate-in fade-in zoom-in-95 duration-200">
        <div className="flex items-center space-x-3 pb-4 border-b border-slate-100">
          <div className="w-10 h-10 rounded-xl bg-amber-50 text-amber-600 flex items-center justify-center shrink-0 border border-amber-200/60 shadow-sm">
            <HelpCircle className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-xl font-bold text-slate-900 tracking-tight">
              偏好決策：選擇本次協助方案
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">
              請在各方案中表達您的看法。提交後將立即執行所選方案。
            </p>
          </div>
        </div>

        <div className="mt-4 p-3.5 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-600 leading-relaxed">
          <p className="font-semibold text-slate-800">作答指南：</p>
          <p>1. 對下方四個方案逐一標記是否可接受（可接受 / 不可接受 / 說不準）。</p>
          <p>2. 點選單選框以指定<strong>本次實際要執行的方案</strong>。</p>
        </div>

        {error && (
          <div className="mt-4 p-3.5 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 text-xs flex items-start space-x-2">
            <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
            <div className="font-medium">{error}</div>
          </div>
        )}

        {validationError && (
          <div className="mt-4 p-3.5 rounded-xl bg-amber-50 border border-amber-200 text-amber-800 text-xs flex items-start space-x-2">
            <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
            <div className="font-medium">{validationError}</div>
          </div>
        )}

        <form onSubmit={handleSubmit} className="mt-6 space-y-4">
          <div className="space-y-3">
            {actionSpecs.map((spec) => {
              const isSelected = selectedActionId === spec.action_id;
              const currentRating = acceptableMap[spec.action_id];

              return (
                <div
                  key={spec.action_id}
                  className={`p-4 rounded-xl border transition-all ${
                    isSelected
                      ? 'border-sky-500 bg-sky-50/40 ring-2 ring-sky-500/20 shadow-sm'
                      : 'border-slate-200 bg-white hover:border-slate-300'
                  }`}
                >
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                    <label className="flex items-start space-x-3 cursor-pointer select-none grow">
                      <input
                        type="radio"
                        name="selected_action"
                        value={spec.action_id}
                        checked={isSelected}
                        onChange={() => handleSelectAction(spec.action_id)}
                        className="mt-1 h-4 w-4 text-sky-600 border-slate-300 focus:ring-sky-500"
                      />
                      <div>
                        <span className="text-sm font-bold text-slate-900 block">
                          {spec.label || spec.name || spec.action_id}
                        </span>
                        <span className="text-xs text-slate-500 block mt-0.5 leading-relaxed">
                          {spec.description}
                        </span>
                      </div>
                    </label>

                    {/* Acceptability radio group */}
                    <div className="shrink-0 flex items-center space-x-1 bg-slate-100 p-1 rounded-lg border border-slate-200/80 self-end sm:self-auto">
                      {(['yes', 'no', 'unsure'] as const).map((val) => (
                        <button
                          key={val}
                          type="button"
                          onClick={() => handleSelectAcceptability(spec.action_id, val)}
                          className={`px-2.5 py-1 text-xs font-semibold rounded-md transition-all ${
                            currentRating === val
                              ? val === 'yes'
                                ? 'bg-emerald-600 text-white shadow-xs'
                                : val === 'no'
                                ? 'bg-rose-600 text-white shadow-xs'
                                : 'bg-slate-700 text-white shadow-xs'
                              : 'text-slate-600 hover:text-slate-900 hover:bg-slate-200/60'
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

          {/* Neutral confirmation if user selects action they marked 'no' (Spec 7.1 / 273) */}
          {isSelectedActionMarkedNo && (
            <div className="p-4 bg-amber-50 border border-amber-200 rounded-xl space-y-2 text-xs text-amber-900">
              <div className="flex items-start space-x-2 font-semibold">
                <ShieldAlert className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
                <span>中性確認提醒：</span>
              </div>
              <p className="pl-6 text-slate-600">
                您將該方案標記為「不可接受」，但同時選擇將其作為本次執行的方案（例如出於不得不選的權衡）。若確定執行，請勾選下方確認方塊：
              </p>
              <label className="flex items-center space-x-2 pl-6 pt-1 cursor-pointer font-medium text-slate-800">
                <input
                  type="checkbox"
                  checked={overrideConfirmed}
                  onChange={(e) => setOverrideConfirmed(e.target.checked)}
                  className="rounded border-slate-300 text-sky-600 focus:ring-sky-500"
                />
                <span>我確認執行此方案 (Override Confirm)</span>
              </label>
            </div>
          )}

          <div>
            <label htmlFor="reason" className="block text-xs font-semibold text-slate-700 mb-1">
              決策理由（可選填短文字）：
            </label>
            <input
              id="reason"
              type="text"
              maxLength={150}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="例如: 想先靠自己試試看，或希望直接得知下一步..."
              className="w-full text-xs py-2 px-3 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-sky-500 placeholder:text-slate-400"
            />
          </div>

          <div className="pt-2 flex justify-end">
            <button
              type="submit"
              disabled={loading}
              className="py-3 px-6 bg-sky-600 hover:bg-sky-700 active:bg-sky-800 text-white font-semibold rounded-xl shadow-md shadow-sky-200 transition-all flex items-center space-x-2 disabled:opacity-50"
            >
              {loading ? (
                <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              ) : (
                <>
                  <Check className="w-4 h-4" />
                  <span>確認並執行此方案</span>
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
