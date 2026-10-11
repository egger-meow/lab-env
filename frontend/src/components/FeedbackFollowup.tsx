import React, { useState } from 'react';
import { ArrowRight, CheckCircle2, HelpCircle, Eye } from 'lucide-react';
import type { TrialStatus } from '../types';

interface FeedbackFollowupProps {
  status: TrialStatus;
  environmentId: string;
  isSolved?: boolean;
  solution?: string[] | null;
  hasFeedbackSubmitted?: boolean;
  onSubmitFeedback: (feedback: Record<string, any>) => Promise<void>;
  onRevealSolution: () => Promise<void>;
  onNext: () => Promise<void>;
  loading: boolean;
  hasNext: boolean;
}

export const FeedbackFollowup: React.FC<FeedbackFollowupProps> = ({
  status,
  environmentId,
  isSolved,
  solution,
  hasFeedbackSubmitted = false,
  onSubmitFeedback,
  onRevealSolution,
  onNext,
  loading,
  hasNext,
}) => {
  const [selectedRating, setSelectedRating] = useState<string | null>(null);
  const [feedbackSent, setFeedbackSent] = useState(hasFeedbackSubmitted);
  const [submittingFeedback, setSubmittingFeedback] = useState(false);
  const [revealingSolution, setRevealingSolution] = useState(false);

  const feedbackOptions = [
    { id: 'too_little', label: '太少' },
    { id: 'just_right', label: '剛好' },
    { id: 'too_much', label: '太多' },
    { id: 'unsure', label: '說不準' },
  ];

  const handleFeedbackSubmit = async () => {
    if (!selectedRating) return;
    setSubmittingFeedback(true);
    try {
      await onSubmitFeedback({ assistance_feedback: selectedRating });
      setFeedbackSent(true);
    } finally {
      setSubmittingFeedback(false);
    }
  };

  const handleRevealSolution = async () => {
    setRevealingSolution(true);
    try {
      await onRevealSolution();
    } finally {
      setRevealingSolution(false);
    }
  };

  const isCompletedDirect = status === 'completed_without_decision';
  const isCompletedWithDecision = status === 'completed';
  const isSkippedOrAborted = status === 'skipped' || status === 'aborted';

  return (
    <div className="bg-white rounded-2xl border border-slate-200 p-6 md:p-8 shadow-sm space-y-6">
      <div className="flex items-center space-x-3 pb-4 border-b border-slate-100">
        <div
          className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${
            isCompletedDirect || isCompletedWithDecision
              ? 'bg-emerald-50 text-emerald-600 border border-emerald-100'
              : 'bg-amber-50 text-amber-600 border border-amber-100'
          }`}
        >
          {isCompletedDirect || isCompletedWithDecision ? (
            <CheckCircle2 className="w-5 h-5" />
          ) : (
            <HelpCircle className="w-5 h-5" />
          )}
        </div>
        <div>
          <h3 className="text-lg font-bold text-slate-900 tracking-tight">
            {isCompletedDirect
              ? '棋盤已在決策前解出'
              : isCompletedWithDecision
              ? '本題已順利完成！'
              : isSkippedOrAborted
              ? `本題已${status === 'skipped' ? '跳過' : '中止'}`
              : '本輪已結束'}
          </h3>
          <p className="text-xs text-slate-500 mt-0.5">
            {isCompletedDirect
              ? '您的作答已成功保存為能力與可用性紀錄。'
              : '感謝您的作答，所有資料已安全保存。'}
          </p>
        </div>
      </div>

      {/* Optional feedback section (Spec 5.4 / 155) */}
      {environmentId === 'puzzle_hints' && (
        <div className="bg-slate-50 rounded-xl p-5 border border-slate-200">
          <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700 mb-2">
            簡短回饋（可選）：您覺得這次獲得的協助如何？
          </h4>
          {feedbackSent ? (
            <div className="text-xs text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg p-2.5 flex items-center gap-1.5 font-medium">
              <CheckCircle2 className="w-4 h-4 shrink-0" />
              感謝您的回饋！此回饋已獨立保存，不會影響主要偏好紀錄。
            </div>
          ) : (
            <div className="space-y-3">
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                {feedbackOptions.map((opt) => (
                  <button
                    key={opt.id}
                    type="button"
                    onClick={() => setSelectedRating(opt.id)}
                    className={`py-2 px-3 text-xs font-semibold rounded-lg border transition-all ${
                      selectedRating === opt.id
                        ? 'bg-sky-600 text-white border-sky-600 shadow-sm'
                        : 'bg-white text-slate-700 border-slate-200 hover:border-slate-300'
                    }`}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
              {selectedRating && (
                <button
                  type="button"
                  onClick={handleFeedbackSubmit}
                  disabled={submittingFeedback}
                  className="px-4 py-1.5 bg-slate-800 hover:bg-slate-900 text-white text-xs font-medium rounded-lg transition-all"
                >
                  {submittingFeedback ? '保存中...' : '送出回饋'}
                </button>
              )}
            </div>
          )}
        </div>
      )}

      {/* Solution reveal followup section (Spec 5.4 / 156) */}
      {environmentId === 'puzzle_hints' && !isSolved && (
        <div className="bg-amber-50/50 rounded-xl p-5 border border-amber-200/60">
          <div className="flex items-center justify-between">
            <div>
              <h4 className="text-xs font-bold text-amber-900 uppercase tracking-wider">
                想了解本題正解嗎？
              </h4>
              <p className="text-xs text-amber-700 mt-0.5">
                點擊可查看完整正確排列。看解法屬於事後 followup 事件，不會修改您已提交的答案。
              </p>
            </div>
            {!solution && (
              <button
                type="button"
                onClick={handleRevealSolution}
                disabled={revealingSolution}
                className="shrink-0 flex items-center space-x-1.5 px-3 py-1.5 bg-white border border-amber-300 text-amber-800 hover:bg-amber-100 rounded-lg text-xs font-semibold transition-all shadow-sm"
              >
                <Eye className="w-3.5 h-3.5" />
                <span>{revealingSolution ? '讀取中...' : '看解法'}</span>
              </button>
            )}
          </div>

          {solution && (
            <div className="mt-4 pt-3 border-t border-amber-200/60">
              <span className="text-xs font-semibold text-slate-600 block mb-2">正確排布：</span>
              <div className="flex gap-2">
                {solution.map((item, idx) => (
                  <div
                    key={idx}
                    className="flex flex-col items-center bg-white border border-slate-300 rounded-lg px-3 py-1.5 shadow-sm text-xs"
                  >
                    <span className="text-slate-400 text-[10px]">第 {idx + 1} 格</span>
                    <span className="font-bold text-slate-800 capitalize mt-0.5">{item}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      <div className="pt-2 flex justify-end">
        <button
          type="button"
          onClick={onNext}
          disabled={loading}
          className="py-3 px-6 bg-sky-600 hover:bg-sky-700 active:bg-sky-800 text-white font-semibold rounded-xl shadow-md shadow-sky-200 transition-all flex items-center space-x-2 disabled:opacity-50"
        >
          {loading ? (
            <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
          ) : (
            <>
              <span>{hasNext ? '前進下一題' : '完成全部試驗'}</span>
              <ArrowRight className="w-4 h-4" />
            </>
          )}
        </button>
      </div>
    </div>
  );
};
