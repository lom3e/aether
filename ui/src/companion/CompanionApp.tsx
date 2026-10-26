import { useContext, useEffect } from 'react';
import './companion.css';
import { useTranslation } from '../i18n';
import { ToastContext } from '../toast';
import { hideCompanion, isTauri } from '../desktop';
import { CompanionPanel } from './CompanionPanel';
import { useCompanionRuntime } from './useCompanionRuntime';
import { getNativeState } from './windowControl';

/**
 * The quick-ask surface: summoned from any app with the shortcut, it is one glass panel with the mini orb and the
 * conversation. There is no floating orb any more: Aether is the orb in its window, and this panel everywhere else.
 */
export function CompanionApp() {
  const { t, language } = useTranslation();
  const showToast = useContext(ToastContext);
  const runtime = useCompanionRuntime();

  useEffect(() => {
    document.documentElement.classList.add('cmp-surface');
    getNativeState().then(s => {
      // macOS gives the panel a frosted-glass sheet (native vibrancy, no shadow): the page draws it flat and translucent.
      if (s?.platform === 'macos') document.documentElement.classList.add('cmp-vibrant');
    });
    return () => document.documentElement.classList.remove('cmp-surface');
  }, []);

  return (
    <div className="cmp-root" data-testid="companion-root" data-mode="panel">
      <CompanionPanel
        runtime={runtime}
        language={language}
        t={t}
        onHide={() => { if (isTauri()) void hideCompanion(); }}
        notify={(m, k) => showToast(m, k)}
      />
    </div>
  );
}
