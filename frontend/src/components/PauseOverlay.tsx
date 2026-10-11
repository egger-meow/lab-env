import React from 'react';
import { PauseCircle, Play } from 'lucide-react';

interface PauseOverlayProps {
  onResume: () => Promise<void>;
  loading: boolean;
}

export const PauseOverlay: React.FC<PauseOverlayProps> = ({ onResume, loading }) => {
  return (
    <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl max-w-sm w-full p-8 text-center border border-slate-200 animate-in fade-in zoom-in-95 duration-200">
        <div className="w-16 h-16 bg-amber-50 text-amber-500 rounded-2xl flex items-center justify-center mx-auto mb-4 border border-amber-100 shadow-sm">
          <PauseCircle className="w-9 h-9" />
        </div>
        <h3 className="text-xl font-bold text-slate-900 tracking-tight">
          試驗已暫停
        </h3>
        <p className="text-sm text-slate-500 mt-2 mb-6 leading-relaxed">
          遊玩計時已停止。您可以放心休息，準備好後隨時點擊下方按鈕繼續。
        </p>

        <button
          onClick={onResume}
          disabled={loading}
          className="w-full py-3.5 px-4 bg-sky-600 hover:bg-sky-700 active:bg-sky-800 text-white font-semibold rounded-xl shadow-md shadow-sky-200 transition-all flex items-center justify-center space-x-2 disabled:opacity-50"
        >
          {loading ? (
            <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
          ) : (
            <>
              <Play className="w-4 h-4 fill-white" />
              <span>繼續試驗</span>
            </>
          )}
        </button>
      </div>
    </div>
  );
};
