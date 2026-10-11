import React, { useState, useEffect } from 'react';
import {
  Download,
  Plus,
  RefreshCw,
  Layers,
  Key,
  AlertCircle,
  Activity,
} from 'lucide-react';
import type { SessionInfo, EventRecord } from '../types';
import { api } from '../api/client';

export const OperatorView: React.FC = () => {
  const [operatorToken, setOperatorToken] = useState<string>(
    localStorage.getItem('preference_lab_operator_token') || 'dev-operator-token-local'
  );
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // New session modal / form
  const [mode, setMode] = useState<string>('pilot');
  const [envOrder, setEnvOrder] = useState<string[]>(['puzzle_hints', 'bret_discrete']);
  const [participantId, setParticipantId] = useState<string>('');
  const [createdSession, setCreatedSession] = useState<{
    session: SessionInfo;
    trial_count: number;
  } | null>(null);

  // Selected session detail
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [sessionDetail, setSessionDetail] = useState<{
    session: SessionInfo;
    trials: any[];
    events: EventRecord[];
    event_count: number;
  } | null>(null);
  const [loadingDetail, setLoadingDetail] = useState<boolean>(false);

  const handleSaveToken = (val: string) => {
    setOperatorToken(val);
    localStorage.setItem('preference_lab_operator_token', val);
  };

  const fetchSessions = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.listSessions(operatorToken);
      setSessions(data);
    } catch (err: any) {
      setError(err.message || '無法取得試驗清單，請確認 Operator Token');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSessions();
  }, [operatorToken]);

  const handleCreateSession = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const res = await api.createSession(
        {
          mode,
          environment_order: envOrder,
          participant_id: participantId.trim() || undefined,
          protocol_id: 'pilot_v001',
        },
        operatorToken
      );
      setCreatedSession(res);
      setParticipantId('');
      await fetchSessions();
    } catch (err: any) {
      setError(err.message || '建立試驗失敗');
    } finally {
      setLoading(false);
    }
  };

  const handleViewDetail = async (sessId: string) => {
    setSelectedSessionId(sessId);
    setLoadingDetail(true);
    try {
      const detail = await api.getSessionDetail(sessId, operatorToken);
      setSessionDetail(detail);
    } catch (err: any) {
      setError(err.message || '取得試驗詳細資料失敗');
    } finally {
      setLoadingDetail(false);
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      {/* Operator Token Bar */}
      <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-xs flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center space-x-3">
          <div className="w-10 h-10 rounded-xl bg-slate-100 text-slate-700 flex items-center justify-center shrink-0 border border-slate-200">
            <Key className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-base font-bold text-slate-900 leading-tight">
              研究者身分授權 (Operator Token)
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              用於調用管理端 API 及匯出資料
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-2 grow sm:grow-0">
          <input
            type="password"
            value={operatorToken}
            onChange={(e) => handleSaveToken(e.target.value)}
            className="font-mono text-xs py-2 px-3 rounded-xl border border-slate-300 focus:outline-none focus:ring-2 focus:ring-sky-500 w-64"
            placeholder="輸入 Operator Token"
          />
          <button
            type="button"
            onClick={fetchSessions}
            className="p-2 text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-xl transition-all"
            title="重新整理"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      {error && (
        <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 text-xs flex items-start space-x-2">
          <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
          <div className="font-medium">{error}</div>
        </div>
      )}

      {/* Grid: Create Session & Session List */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Create Session Form */}
        <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-xs space-y-5">
          <div className="flex items-center space-x-2.5 pb-3 border-b border-slate-100">
            <Plus className="w-5 h-5 text-sky-600" />
            <h3 className="text-base font-bold text-slate-900">建立新受試者 Session</h3>
          </div>

          <form onSubmit={handleCreateSession} className="space-y-4">
            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1.5">
                試驗模式 (Mode)
              </label>
              <select
                value={mode}
                onChange={(e) => setMode(e.target.value)}
                className="w-full text-xs py-2 px-3 rounded-xl border border-slate-300 focus:outline-none focus:ring-2 focus:ring-sky-500"
              >
                <option value="pilot">先導試驗 (Pilot / 4 題 + 2 教學/練習)</option>
                <option value="practice">純練習模式 (Practice)</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1.5">
                環境執行順序 (Environment Order)
              </label>
              <div className="space-y-2">
                <label className="flex items-center space-x-2 text-xs text-slate-700 cursor-pointer">
                  <input
                    type="radio"
                    name="env_order"
                    checked={envOrder[0] === 'puzzle_hints'}
                    onChange={() => setEnvOrder(['puzzle_hints', 'bret_discrete'])}
                    className="text-sky-600"
                  />
                  <span>1. Puzzle Hints → 2. BRET Discrete</span>
                </label>
                <label className="flex items-center space-x-2 text-xs text-slate-700 cursor-pointer">
                  <input
                    type="radio"
                    name="env_order"
                    checked={envOrder[0] === 'bret_discrete'}
                    onChange={() => setEnvOrder(['bret_discrete', 'puzzle_hints'])}
                    className="text-sky-600"
                  />
                  <span>1. BRET Discrete → 2. Puzzle Hints</span>
                </label>
              </div>
            </div>

            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1.5">
                受試者代號（選填，留空自動匿名生成）
              </label>
              <input
                type="text"
                value={participantId}
                onChange={(e) => setParticipantId(e.target.value)}
                placeholder="例如: P_001"
                className="w-full text-xs py-2 px-3 rounded-xl border border-slate-300 focus:outline-none focus:ring-2 focus:ring-sky-500 font-mono"
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-3 px-4 bg-sky-600 hover:bg-sky-700 text-white font-semibold rounded-xl text-xs shadow-md shadow-sky-200 transition-all flex items-center justify-center space-x-2 disabled:opacity-50"
            >
              <span>建立 Session 並初始化試驗</span>
            </button>
          </form>

          {createdSession && (
            <div className="p-4 rounded-xl bg-emerald-50 border border-emerald-200 text-xs text-emerald-950 space-y-2">
              <span className="font-bold block text-emerald-800">建立成功！</span>
              <p>
                受試者代碼：
                <strong className="font-mono text-sm tracking-wider ml-1 bg-white px-2 py-0.5 rounded border border-emerald-300 text-emerald-900">
                  {createdSession.session.session_code}
                </strong>
              </p>
              <p className="text-[11px] text-emerald-700">
                可將此代碼提供給受試者，或切換至「受試者視角」直接輸入進行測試。
              </p>
            </div>
          )}
        </div>

        {/* Sessions List */}
        <div className="lg:col-span-2 bg-white rounded-2xl border border-slate-200 p-6 shadow-xs space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-slate-100">
            <h3 className="text-base font-bold text-slate-900 flex items-center space-x-2">
              <Layers className="w-5 h-5 text-indigo-600" />
              <span>所有試驗 Session ({sessions.length})</span>
            </h3>
            <span className="text-xs text-slate-400">點擊查看詳情與一鍵匯出</span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 text-slate-500 font-bold uppercase tracking-wider border-b border-slate-200">
                <tr>
                  <th className="py-2.5 px-3">Session 代碼</th>
                  <th className="py-2.5 px-3">受試者 ID</th>
                  <th className="py-2.5 px-3">模式</th>
                  <th className="py-2.5 px-3">狀態</th>
                  <th className="py-2.5 px-3">建立時間</th>
                  <th className="py-2.5 px-3 text-right">操作</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {sessions.map((s) => {
                  const isSelected = selectedSessionId === s.session_id;
                  return (
                    <tr
                      key={s.session_id}
                      onClick={() => handleViewDetail(s.session_id)}
                      className={`cursor-pointer transition-colors ${
                        isSelected ? 'bg-sky-50/60' : 'hover:bg-slate-50'
                      }`}
                    >
                      <td className="py-3 px-3 font-mono font-bold text-slate-900">
                        {s.session_code}
                      </td>
                      <td className="py-3 px-3 font-mono text-slate-600">
                        {s.participant_id}
                      </td>
                      <td className="py-3 px-3 capitalize text-slate-700">
                        {s.mode}
                      </td>
                      <td className="py-3 px-3">
                        <span
                          className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                            s.status === 'completed'
                              ? 'bg-emerald-100 text-emerald-800'
                              : 'bg-amber-100 text-amber-800'
                          }`}
                        >
                          {s.status}
                        </span>
                      </td>
                      <td className="py-3 px-3 text-slate-400 font-mono text-[11px]">
                        {new Date(s.created_at).toLocaleTimeString()}
                      </td>
                      <td className="py-3 px-3 text-right">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleViewDetail(s.session_id);
                          }}
                          className="text-xs font-semibold text-sky-600 hover:text-sky-800 underline"
                        >
                          檢視
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Session Detail Modal / Drawer */}
      {selectedSessionId && (
        loadingDetail ? (
          <div className="bg-white rounded-2xl border border-slate-200 p-8 text-center text-slate-500 shadow-xs flex items-center justify-center space-x-2">
            <RefreshCw className="w-5 h-5 animate-spin text-sky-600" />
            <span>載入試驗詳細資料中...</span>
          </div>
        ) : sessionDetail ? (
          <div className="bg-white rounded-2xl border border-slate-200 p-6 md:p-8 shadow-xs space-y-6 animate-in fade-in duration-150">
          <div className="flex flex-wrap items-center justify-between gap-4 pb-4 border-b border-slate-100">
            <div>
              <div className="flex items-center space-x-2">
                <span className="text-xl font-bold text-slate-900 font-mono">
                  {sessionDetail.session.session_code}
                </span>
                <span className="text-xs px-2.5 py-0.5 rounded-full bg-slate-100 text-slate-700 font-bold">
                  {sessionDetail.session.mode}
                </span>
              </div>
              <p className="text-xs text-slate-500 mt-1">
                Session ID: <span className="font-mono">{sessionDetail.session.session_id}</span> |
                Participant: <span className="font-mono">{sessionDetail.session.participant_id}</span>
              </p>
            </div>

            <div className="flex items-center space-x-3">
              {/* One-click Export ZIP button (Spec 10.4) */}
              <a
                href={api.getExportZipUrl(sessionDetail.session.session_id)}
                download
                className="py-2.5 px-4 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-xs font-semibold shadow-md shadow-emerald-200 transition-all flex items-center space-x-1.5"
              >
                <Download className="w-4 h-4" />
                <span>匯出完整 Session ZIP</span>
              </a>
              <button
                type="button"
                onClick={() => setSelectedSessionId(null)}
                className="py-2.5 px-4 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl text-xs font-semibold transition-all"
              >
                關閉
              </button>
            </div>
          </div>

          {/* Trials Table */}
          <div>
            <h4 className="text-xs font-bold text-slate-700 uppercase tracking-wider mb-3">
              試驗題目清單與完成狀態 ({sessionDetail.trials.length})
            </h4>
            <div className="overflow-x-auto border border-slate-200 rounded-xl">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-50 text-slate-500 font-bold uppercase tracking-wider border-b border-slate-200">
                  <tr>
                    <th className="py-2 px-3">#</th>
                    <th className="py-2 px-3">環境</th>
                    <th className="py-2 px-3">題號 (item_id)</th>
                    <th className="py-2 px-3">狀態</th>
                    <th className="py-2 px-3">遊玩時間</th>
                    <th className="py-2 px-3">已選行動</th>
                    <th className="py-2 px-3">正解/結算</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {sessionDetail.trials.map((t, idx) => (
                    <tr key={t.trial_id} className="hover:bg-slate-50/50">
                      <td className="py-2.5 px-3 font-bold text-slate-400">{idx + 1}</td>
                      <td className="py-2.5 px-3 font-medium text-slate-700">{t.environment_id}</td>
                      <td className="py-2.5 px-3 font-mono text-slate-900">{t.item_id}</td>
                      <td className="py-2.5 px-3">
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                            t.status.includes('completed')
                              ? 'bg-emerald-100 text-emerald-800'
                              : t.status === 'active'
                              ? 'bg-sky-100 text-sky-800'
                              : 'bg-slate-100 text-slate-600'
                          }`}
                        >
                          {t.status}
                        </span>
                      </td>
                      <td className="py-2.5 px-3 font-mono text-slate-600">
                        {Math.floor((t.active_play_ms || 0) / 1000)}s
                      </td>
                      <td className="py-2.5 px-3 font-mono text-indigo-700 font-semibold">
                        {t.decision?.selected_action_id || '-'}
                      </td>
                      <td className="py-2.5 px-3">
                        {t.outcome ? (
                          <span className="font-mono text-slate-700">
                            {JSON.stringify(t.outcome.result_summary)}
                          </span>
                        ) : t.public_state?.is_solved ? (
                          <span className="text-emerald-600 font-bold">已解出</span>
                        ) : (
                          '-'
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Event Stream Log */}
          <div>
            <h4 className="text-xs font-bold text-slate-700 uppercase tracking-wider mb-3 flex items-center gap-1.5">
              <Activity className="w-4 h-4 text-sky-600" />
              <span>有序事件日誌 (Event Stream - 共 {sessionDetail.events?.length || 0} 筆)</span>
            </h4>
            <div className="max-h-64 overflow-y-auto border border-slate-200 rounded-xl bg-slate-900 text-slate-200 p-4 font-mono text-xs space-y-1.5">
              {(sessionDetail.events || []).map((ev) => (
                <div key={ev.event_id} className="leading-relaxed hover:bg-slate-800/60 px-1 rounded">
                  <span className="text-slate-500 mr-2">#{ev.sequence_no}</span>
                  <span className="text-sky-400 font-bold mr-2">[{ev.event_type}]</span>
                  <span className="text-amber-300 mr-2">trial:{ev.trial_id.slice(-6)}</span>
                  <span className="text-slate-300">{JSON.stringify(ev.payload)}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : null
    )}
    </div>
  );
};
