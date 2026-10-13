import React, { useState, useEffect, useRef } from 'react';
import { Navbar } from './components/Navbar';
import { SessionJoin } from './components/SessionJoin';
import { PauseOverlay } from './components/PauseOverlay';
import { PuzzleView } from './components/PuzzleView';
import { BretView } from './components/BretView';
import { OperatorView } from './components/OperatorView';
import { api, ApiError, pendingKey } from './api/client';
import type { ParticipantTrialView, SessionInfo } from './types';
import { CheckCircle2, RotateCcw } from 'lucide-react';

export const App: React.FC = () => {
  const [viewMode, setViewMode] = useState<'participant' | 'operator'>(
    new URLSearchParams(location.search).get('view') === 'operator' ? 'operator' :
    (localStorage.getItem('preference_lab_view_mode') as 'participant' | 'operator') || 'participant'
  );

  // Participant state
  const [sessionCode, setSessionCode] = useState<string>(
    localStorage.getItem('preference_lab_session_code') || ''
  );
  const [sessionToken, setSessionToken] = useState<string>(
    localStorage.getItem('preference_lab_session_token') || ''
  );
  const [sessionInfo, setSessionInfo] = useState<SessionInfo | null>(null);
  const [currentTrial, setCurrentTrial] = useState<ParticipantTrialView | null>(null);
  const [totalTrials, setTotalTrials] = useState<number>(0);
  const [sessionCompleted, setSessionCompleted] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(false);
  const [joinError, setJoinError] = useState<string | null>(null);
  const [syncToast, setSyncToast] = useState<string | null>(null);

  const handleViewModeChange = (mode: 'participant' | 'operator') => {
    setViewMode(mode);
    localStorage.setItem('preference_lab_view_mode', mode);
  };

  const restoreStartedRef = useRef(false);
  // Restore session on initial load (handles page refresh & recovery)
  useEffect(() => {
    if (restoreStartedRef.current) return;
    restoreStartedRef.current = true;
    const savedCode = localStorage.getItem('preference_lab_session_code');
    if (savedCode && viewMode === 'participant') {
      handleJoinSession(savedCode, false);
    }
  }, []);

  useEffect(() => {
    const conflict = (event: Event) => {
      const fresh = (event as CustomEvent<ParticipantTrialView>).detail;
      setCurrentTrial(previous => previous?.trial_id === fresh.trial_id ? fresh : previous);
      showSyncToast('其他視窗已更新資料，已同步畫面；請檢查後重新確認操作。');
    };
    window.addEventListener('preference-lab-conflict', conflict);
    return () => window.removeEventListener('preference-lab-conflict', conflict);
  }, []);

  const handleJoinSession = async (code: string, clearOnError = true) => {
    setLoading(true);
    setJoinError(null);
    try {
      const res = await api.joinSession(code);
      setSessionCode(code);
      setSessionToken(res.session_token);
      setSessionInfo(res.session);
      setTotalTrials(res.total_trials);
      setSessionCompleted(res.session_completed);

      localStorage.setItem('preference_lab_session_code', code);
      localStorage.setItem('preference_lab_session_token', res.session_token);

      if (res.session_completed) {
        setCurrentTrial(null);
      } else if (res.current_trial_id) {
        const pending = localStorage.getItem(pendingKey(res.current_trial_id));
        if (pending) {
          try { await api.commitDecision(res.current_trial_id, JSON.parse(pending), res.session_token); }
          catch { showSyncToast('仍有待確認決策，請重試原提交；已保留請求與草稿'); }
        }
        const trialData = await api.getTrial(res.current_trial_id, res.session_token);
        setCurrentTrial(trialData);
      }
    } catch (err: any) {
      if (clearOnError) {
        setJoinError(err.message || '加入試驗失敗，請檢查代碼是否正確');
      } else {
        if (err instanceof ApiError && err.status === 404) handleLeaveSession();
        else setJoinError('暫時無法恢復連線；代碼、草稿與待確認請求已保留，請重試。');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleLeaveSession = () => {
    setSessionCode('');
    setSessionToken('');
    setSessionInfo(null);
    setCurrentTrial(null);
    setSessionCompleted(false);
    localStorage.removeItem('preference_lab_session_code');
    localStorage.removeItem('preference_lab_session_token');
  };

  const advancingRef = useRef(false);
  const handleNextTrial = async () => {
    if (!currentTrial || !sessionInfo || advancingRef.current) return;
    advancingRef.current = true;
    setLoading(true);
    try {
      const res = await api.nextTrial(
        currentTrial.trial_id,
        sessionInfo.session_id,
        sessionToken
      );

      if (res.session_completed) {
        setSessionCompleted(true);
        setCurrentTrial(null);
      } else if (res.has_next && res.next_trial_id) {
        const nextTrialData = await api.getTrial(res.next_trial_id, sessionToken);
        setCurrentTrial(nextTrialData);
      }
    } catch (err: any) {
      if (err instanceof ApiError && err.isStateVersionConflict) {
        showSyncToast('狀態衝突，已自動為您同步');
        const fresh = await api.getTrial(currentTrial.trial_id, sessionToken);
        setCurrentTrial(fresh);
      } else {
        showSyncToast(err.message || '無法切換至下一題');
      }
    } finally {
      advancingRef.current = false;
      setLoading(false);
    }
  };

  const handlePause = async (activePlayMs: number) => {
    if (!currentTrial || !['active', 'decision_open'].includes(currentTrial.status)) return;
    const trialId = currentTrial.trial_id;
    const syncTrial = async () => {
      const fresh = await api.getTrial(trialId, sessionToken);
      setCurrentTrial(previous => previous?.trial_id === trialId && fresh.state_version >= previous.state_version ? fresh : previous);
    };
    try {
      await api.pauseTrial(trialId, activePlayMs, currentTrial.state_version, sessionToken);
      await syncTrial();
    } catch (err: any) {
      if (err instanceof ApiError && err.isStateVersionConflict) {
        try { await syncTrial(); }
        catch { showSyncToast('暫時無法同步暫停狀態，請確認連線後重試。'); }
      } else {
        // Native alerts cause another blur and can recursively request pause.
        showSyncToast(err.message || '暫停失敗，請確認連線後重試。');
      }
    }
  };

  const handleResume = async () => {
    if (!currentTrial) return;
    setLoading(true);
    try {
      await api.resumeTrial(
        currentTrial.trial_id,
        currentTrial.state_version,
        sessionToken
      );
      const fresh = await api.getTrial(currentTrial.trial_id, sessionToken);
      setCurrentTrial(fresh);
    } catch (err: any) {
      showSyncToast(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSkip = async (activePlayMs: number) => {
    if (!currentTrial) return;
    if (loading) return;
    setLoading(true);

    try {
      await api.skipTrial(
        currentTrial.trial_id,
        'participant_skip',
        activePlayMs,
        currentTrial.state_version,
        sessionToken
      );
      const fresh = await api.getTrial(currentTrial.trial_id, sessionToken);
      setCurrentTrial(fresh);
    } catch (err: any) {
      showSyncToast(err.message);
    } finally {
      setLoading(false);
    }
  };

  function showSyncToast(msg: string) {
    setSyncToast(msg);
    setTimeout(() => setSyncToast(null), 3500);
  }

  const updateCurrentTrial = (fresh: ParticipantTrialView) => {
    setCurrentTrial(previous => previous?.trial_id === fresh.trial_id && fresh.state_version >= previous.state_version ? fresh : previous);
  };

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col font-sans text-slate-900">
      <Navbar
        viewMode={viewMode}
        onViewModeChange={handleViewModeChange}
        sessionCode={sessionCode}
        participantId={sessionInfo?.participant_id}
        onLeaveSession={handleLeaveSession}
      />

      {syncToast && (
        <div role="status" className="pointer-events-none fixed bottom-5 right-5 z-50 bg-slate-900 text-white text-xs px-4 py-2.5 rounded-xl shadow-xl flex items-center space-x-2 animate-in fade-in slide-in-from-bottom-2">
          <RotateCcw className="w-3.5 h-3.5 text-sky-400 animate-spin" />
          <span>{syncToast}</span>
        </div>
      )}

      <main className="grow py-4 px-4 sm:px-6 lg:px-8 max-w-5xl mx-auto w-full">
        {viewMode === 'operator' ? (
          <OperatorView />
        ) : !sessionCode || !sessionInfo ? (
          <SessionJoin
            defaultSessionCode={sessionCode}
            onJoin={handleJoinSession}
            loading={loading}
            error={joinError}
          />
        ) : sessionCompleted ? (
          /* Entire Session Completed Screen */
          <div className="bg-white rounded-2xl border border-slate-200 p-8 md:p-12 text-center max-w-xl mx-auto my-12 shadow-sm space-y-6">
            <div className="w-16 h-16 bg-emerald-50 text-emerald-600 rounded-3xl flex items-center justify-center mx-auto border border-emerald-100 shadow-xs">
              <CheckCircle2 className="w-9 h-9" />
            </div>
            <div>
              <h2 className="text-2xl font-bold text-slate-900 tracking-tight">
                您已完成本次試驗的所有題目！
              </h2>
              <p className="text-sm text-slate-500 mt-2 leading-relaxed">
                非常感謝您的參與與協助！您的所有回答與決策資料已完整儲存至本地研究資料庫中。
              </p>
            </div>
            <div className="p-4 bg-slate-50 rounded-xl border border-slate-200 text-xs text-slate-600 space-y-1">
              <p>
                Session Code: <strong className="font-mono text-slate-800">{sessionCode}</strong>
              </p>
              <p>
                受試者代號: <strong className="font-mono text-slate-800">{sessionInfo.participant_id}</strong>
              </p>
            </div>
            <button
              type="button"
              onClick={handleLeaveSession}
              className="py-3 px-6 bg-slate-800 hover:bg-slate-900 text-white font-semibold rounded-xl text-xs transition-all"
            >
              返回入口頁面
            </button>
          </div>
        ) : currentTrial ? (
          <>
            {/* Trial Progress Bar */}
            <div className="mb-4 bg-white rounded-xl border border-slate-200 px-4 py-3 flex items-center justify-between text-xs text-slate-500 shadow-2xs">
              <div className="flex items-center space-x-2 font-medium">
                <span className="text-slate-800 font-bold">
                  第 {currentTrial.collection_index + 1} 題 / 共 {totalTrials} 題
                </span>
                <span className="text-slate-300">|</span>
                <span className="capitalize text-slate-600">
                  {currentTrial.environment_id === 'puzzle_hints' ? 'Puzzle Hints' : 'BRET Discrete'}
                </span>
              </div>
              <div className="w-36 sm:w-48 bg-slate-100 h-2 rounded-full overflow-hidden">
                <div
                  className="bg-sky-600 h-full rounded-full transition-all duration-300"
                  style={{
                    width: `${Math.round(((currentTrial.collection_index + 1) / totalTrials) * 100)}%`,
                  }}
                />
              </div>
            </div>

            {/* Trial Views by Environment */}
            {currentTrial.environment_id === 'puzzle_hints' ? (
              <PuzzleView
                key={currentTrial.trial_id}
                trial={currentTrial}
                sessionToken={sessionToken}
                onTrialUpdated={updateCurrentTrial}
                navigating={loading}
                onNextTrial={handleNextTrial}
                onPause={handlePause}
                onSkip={handleSkip}
                hasNext={currentTrial.collection_index + 1 < totalTrials}
              />
            ) : (
              <BretView
                onPause={handlePause}
                key={currentTrial.trial_id}
                trial={currentTrial}
                sessionToken={sessionToken}
                onTrialUpdated={updateCurrentTrial}
                navigating={loading}
                onNextTrial={handleNextTrial}
                onSkip={handleSkip}
                hasNext={currentTrial.collection_index + 1 < totalTrials}
              />
            )}

            {/* Pause Overlay */}
            {currentTrial.status === 'paused' && (
              <PauseOverlay onResume={handleResume} loading={loading} />
            )}
          </>
        ) : (
          <div className="text-center py-24 text-slate-400">載入試驗資料中...</div>
        )}
      </main>
    </div>
  );
};

export default App;
