import { useCallback, useContext, useEffect, useState } from 'react';
import './companion.css';
import { useTranslation } from '../i18n';
import { ToastContext } from '../toast';
import { hideCompanion } from '../desktop';
import { CompanionOrb } from './CompanionOrb';
import { CompanionPanel } from './CompanionPanel';
import { STATUS_LABEL_KEYS } from './status';
import { useCompanionRuntime } from './useCompanionRuntime';
import { getNativeState, onNativeModeChange, setNativeFollow, setNativeMode, type CompanionMode } from './windowControl';
import { isTauri } from '../desktop';

const FOLLOW_KEY = 'aether_companion_follow';

function initialBrowserMode(): CompanionMode {
  // Outside Tauri (tests, dev server) the mode can be chosen with ?mode=orb|panel.
  const m = new URLSearchParams(window.location.search).get('mode');
  return m === 'orb' ? 'orb' : 'panel';
}

/** The Companion surface: owns the orb/panel mode and wires the panel to the shared runtime. */
export function CompanionApp() {
  const { t, language } = useTranslation();
  const showToast = useContext(ToastContext);
  const runtime = useCompanionRuntime();
  const [mode, setMode] = useState<CompanionMode>(initialBrowserMode);
  const [follow, setFollow] = useState<boolean>(() => {
    try {
      return localStorage.getItem(FOLLOW_KEY) === '1';
    } catch {
      return false;
    }
  });

  useEffect(() => {
    document.documentElement.classList.add('cmp-surface');
    return () => document.documentElement.classList.remove('cmp-surface');
  }, []);

  // Sync with the native window: initial mode, later changes (shortcut, tray), and the stored follow preference.
  useEffect(() => {
    getNativeState().then(s => {
      if (!s) return;
      setMode(s.mode);
    });
    setNativeFollow(follow);
    return onNativeModeChange(setMode);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const requestMode = useCallback(async (next: CompanionMode) => {
    if (isTauri()) await setNativeMode(next); // the native side resizes first, then announces the mode
    else setMode(next);
  }, []);

  const toggleFollow = useCallback(() => {
    setFollow(prev => {
      const next = !prev;
      try {
        localStorage.setItem(FOLLOW_KEY, next ? '1' : '0');
      } catch {
        /* preference just won't persist */
      }
      setNativeFollow(next);
      return next;
    });
  }, []);

  const label = `Aether — ${t(STATUS_LABEL_KEYS[runtime.status])}`;

  return (
    <div className="cmp-root" data-testid="companion-root" data-mode={mode}>
      {mode === 'orb' ? (
        <CompanionOrb status={runtime.status} label={`${label}. ${t('cmpOrbOpenHint')}`} badge={runtime.approvals.length} onOpen={() => requestMode('panel')} />
      ) : (
        <CompanionPanel
          runtime={runtime}
          language={language}
          t={t}
          follow={follow}
          onToggleFollow={toggleFollow}
          onCollapse={() => requestMode('orb')}
          onHide={() => (isTauri() ? hideCompanion() : setMode('orb'))}
          notify={(m, k) => showToast(m, k)}
        />
      )}
    </div>
  );
}
