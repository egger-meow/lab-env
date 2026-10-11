import React, { useState } from 'react';
import { LogIn, Sparkles, AlertCircle } from 'lucide-react';

interface SessionJoinProps {
  onJoin: (sessionCode: string) => Promise<void>;
  loading: boolean;
  error?: string | null;
  defaultSessionCode?: string;
}

export const SessionJoin: React.FC<SessionJoinProps> = ({
  onJoin,
  loading,
  error,
  defaultSessionCode = '',
}) => {
  const [sessionCode, setSessionCode] = useState(defaultSessionCode);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const cleanCode = sessionCode.trim().toUpperCase();
    if (cleanCode) {
      onJoin(cleanCode);
    }
  };

  return (
    <div className="max-w-md mx-auto my-12 px-4">
      <div className="bg-white rounded-2xl shadow-xl shadow-slate-200/60 border border-slate-200 p-8">
        <div className="text-center mb-6">
          <div className="w-14 h-14 bg-sky-50 text-sky-600 rounded-2xl flex items-center justify-center mx-auto mb-4 border border-sky-100 shadow-sm">
            <Sparkles className="w-7 h-7" />
          </div>
          <h2 className="text-2xl font-bold text-slate-900 tracking-tight">
            加入研究試驗
          </h2>
          <p className="text-sm text-slate-500 mt-2 leading-relaxed">
            歡迎參與實驗！請輸入研究人員提供的 PL-XXXX 格式代碼以開始試驗。
          </p>
        </div>

        <div className="bg-slate-50 rounded-xl p-4 border border-slate-200 mb-6 text-xs text-slate-600 space-y-1.5 leading-relaxed">
          <p className="font-semibold text-slate-800 flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-sky-500"></span>
            重要研究說明：
          </p>
          <p>• 本研究旨在了解人在不同情況下的偏好決策，<strong>沒有研究者期待的標準答案</strong>。</p>
          <p>• 請依據您當下最真實的想法與選擇進行操作即可。</p>
          <p>• 您隨時可以按暫停休息或停止退出。</p>
        </div>

        {error && (
          <div className="mb-6 p-3.5 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 text-xs flex items-start space-x-2">
            <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
            <div className="font-medium">{error}</div>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="session-code" className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-2">
              試驗代碼 (Session Code)
            </label>
            <input
              id="session-code"
              type="text"
              required
              maxLength={8}
              value={sessionCode}
              onChange={(e) => setSessionCode(e.target.value.toUpperCase())}
              placeholder="例如: PL-1A2B"
              className="w-full text-center tracking-widest text-2xl font-mono font-bold uppercase py-3 px-4 rounded-xl border border-slate-300 focus:outline-none focus:ring-2 focus:ring-sky-500 focus:border-transparent transition-all placeholder:text-slate-300 placeholder:font-normal placeholder:tracking-normal placeholder:text-base"
            />
          </div>

          <button
            type="submit"
            disabled={loading || !sessionCode.trim()}
            className="w-full py-3.5 px-4 bg-sky-600 hover:bg-sky-700 active:bg-sky-800 text-white font-semibold rounded-xl shadow-md shadow-sky-200 transition-all flex items-center justify-center space-x-2 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? (
              <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            ) : (
              <>
                <LogIn className="w-4 h-4" />
                <span>進入試驗</span>
              </>
            )}
          </button>
        </form>
      </div>
    </div>
  );
};
