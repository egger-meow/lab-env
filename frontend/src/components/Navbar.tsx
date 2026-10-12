import React from 'react';
import { useTheme } from '../useTheme';
import { FlaskConical, Settings, User, Moon, Sun } from 'lucide-react';

interface NavbarProps {
  viewMode: 'participant' | 'operator';
  onViewModeChange: (mode: 'participant' | 'operator') => void;
  sessionCode?: string;
  participantId?: string;
  onLeaveSession?: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({
  viewMode,
  onViewModeChange,
  sessionCode,
  participantId,
  onLeaveSession,
}) => {
  const { theme, toggleTheme } = useTheme();

  return (
    <header className="bg-white border-b border-slate-200 sticky top-0 z-30 shadow-sm">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="w-10 h-10 rounded-xl bg-sky-600 flex items-center justify-center text-white shadow-md shadow-sky-200">
            <FlaskConical className="w-5 h-5" />
          </div>
          <div>
            <h1 className="text-lg font-bold text-slate-900 tracking-tight leading-none">
              Preference Lab
            </h1>
            <p className="text-xs text-slate-500 font-medium mt-0.5">
              環境偏好研究原型 (M1)
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-3">
          {sessionCode && viewMode === 'participant' && (
            <div className="hidden sm:flex items-center space-x-2 bg-slate-100 rounded-lg px-3 py-1.5 border border-slate-200 text-xs">
              <span className="text-slate-500">Session:</span>
              <span className="font-mono font-bold text-slate-800">{sessionCode}</span>
              {participantId && (
                <>
                  <span className="text-slate-300">|</span>
                  <span className="text-slate-500">ID:</span>
                  <span className="font-mono text-slate-700">{participantId}</span>
                </>
              )}
              {onLeaveSession && (
                <button
                  onClick={onLeaveSession}
                  className="ml-2 text-rose-600 hover:text-rose-800 font-medium underline"
                >
                  離開
                </button>
              )}
            </div>
          )}

          <button
            type="button"
            onClick={toggleTheme}
            aria-label={theme === 'dark' ? '切換至淺色模式' : '切換至深色模式'}
            title={theme === 'dark' ? '切換至淺色模式' : '切換至深色模式'}
            className="shrink-0 rounded-lg border border-slate-200 bg-slate-100 p-2 text-slate-600 hover:text-slate-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-500"
          >
            {theme === 'dark' ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
          </button>

          <div className="flex rounded-lg bg-slate-100 p-1 border border-slate-200">
            <button
              onClick={() => onViewModeChange('participant')}
              className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-md text-xs font-semibold transition-all ${
                viewMode === 'participant'
                  ? 'bg-white text-sky-700 shadow-sm'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <User className="w-3.5 h-3.5" />
              <span>受試者視角</span>
            </button>
            <button
              onClick={() => onViewModeChange('operator')}
              className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-md text-xs font-semibold transition-all ${
                viewMode === 'operator'
                  ? 'bg-white text-sky-700 shadow-sm'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <Settings className="w-3.5 h-3.5" />
              <span>研究者後台</span>
            </button>
          </div>
        </div>
      </div>
    </header>
  );
};
