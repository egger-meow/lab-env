import React, { useState, useRef } from 'react';
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

  const [advancing, setAdvancing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const busyRef = useRef(false);
  const busy = loading || submittingFeedback || revealingSolution || advancing;

  const feedbackOptions = [
    { id: 'too_little', label: '太少' },
    { id: 'just_right', label: '剛好' },
    { id: 'too_much', label: '太多' },
    { id: 'unsure', label: '說不準' },
  ];

  const handleFeedbackSubmit = async (rating: string) => {
    if (busyRef.current || loading) return;
    busyRef.current = true;
    setSelectedRating(rating);
    setError(null);
    setSubmittingFeedback(true);
    try {
      await onSubmitFeedback({ assistance_feedback: rating });
      setFeedbackSent(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : '回饋保存失敗，請重試。');
    } finally {
      busyRef.current = false;
      setSubmittingFeedback(false);
    }
  };

  const handleRevealSolution = async () => {
    if (busyRef.current || loading) return;
    busyRef.current = true;
    setError(null);
    setRevealingSolution(true);
    try {
      await onRevealSolution();
    } catch (err) {
      setError(err instanceof Error ? err.message : '解法讀取失敗，請重試。');
    } finally {
      busyRef.current = false;
      setRevealingSolution(false);
    }
  };

  const handleNext = async () => {
    if (busyRef.current || loading) return;
    busyRef.current = true;
    setAdvancing(true);
    setError(null);
    try { await onNext(); }
    catch (err) { setError(err instanceof Error ? err.message : '切換失敗，請重試。'); }
    finally { busyRef.current = false; setAdvancing(false); }
  };
  const puzzleSolved = environmentId === 'puzzle_hints' && Boolean(isSolved);
  const completed = status === 'completed' || status === 'completed_without_decision';
  const successful = completed && (environmentId !== 'puzzle_hints' || puzzleSolved);
  const isCompletedDirect = status === 'completed_without_decision';
  const isCompletedWithDecision = status === 'completed';
  const isSkippedOrAborted = status === 'skipped' || status === 'aborted';

  return (
    <div className="bg-white rounded-2xl border border-slate-200 p-6 md:p-8 shadow-sm space-y-6">
      <div className="flex items-center space-x-3 pb-4 border-b border-slate-100">
        <div
          className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${
            successful
              ? 'bg-emerald-50 text-emerald-600 border border-emerald-100'
              : 'bg-amber-50 text-amber-600 border border-amber-100'
          }`}
        >
          {successful ? (
            <CheckCircle2 className="w-5 h-5" />
          ) : (
            <HelpCircle className="w-5 h-5" />
          )}
        </div>
        <div>
          <h3 className="text-lg font-bold text-slate-900 tracking-tight">
            {isCompletedDirect
              ? '棋盤已解出'
              : isCompletedWithDecision
              ? (environmentId === 'puzzle_hints' ? (puzzleSolved ? '棋盤已解出' : '本輪已結束，棋盤尚未解出') : '本輪已完成')
              : isSkippedOrAborted
              ? `本題已${status === 'skipped' ? '跳過' : '中止'}`
              : '本輪已結束'}
          </h3>
          <p className="text-xs text-slate-500 mt-0.5">
            {isCompletedDirect
              ? '您的作答已成功保存為能力與可用性紀錄。'
              : '本輪作答紀錄已保存。您可以前進下一題。'}
          </p>
        </div>
      </div>

      {error && <p role="alert" className="text-sm text-rose-700">{error}</p>}
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
                    onClick={() => void handleFeedbackSubmit(opt.id)}
                    disabled={busy}
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
              {submittingFeedback && <p role="status" className="text-xs text-slate-500">保存中...</p>}
            </div>
          )}
        </div>
      )}

      {/* Solution reveal followup section (Spec 5.4 / 156) */}
      {environmentId === 'puzzle_hints' && !isSolved && status !== 'aborted' && (
        <div className="bg-amber-50/50 rounded-xl p-5 border border-amber-200/60">
          <div className="flex items-center justify-between">
            <div>
              <h4 className="text-xs font-bold text-amber-900 uppercase tracking-wider">
                想了解本題正解嗎？
              </h4>
              <p className="text-xs text-amber-700 mt-0.5">
                點擊可查看完整正確排列。不會修改您已提交的答案。
              </p>
            </div>
            {!solution && (
              <button
                type="button"
                onClick={handleRevealSolution}
                disabled={busy}
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
          onClick={handleNext}
          disabled={busy}
          className="py-3 px-6 bg-sky-600 hover:bg-sky-700 active:bg-sky-800 text-white font-semibold rounded-xl shadow-md shadow-sky-200 transition-all flex items-center space-x-2 disabled:opacity-50"
        >
          {loading || advancing ? (
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
