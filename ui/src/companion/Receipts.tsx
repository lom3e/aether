import { useState } from 'react';
import { apiUrl } from '../api';
import type { TranslationKey } from '../i18n';
import type { AnswerSource, ChatMessage } from './useCompanionRuntime';

type T = (key: TranslationKey, params?: Record<string, string | number>) => string;

interface Props {
  message: ChatMessage;
  t: T;
  notify: (message: string, kind: 'success' | 'error' | 'info' | 'warning') => void;
}

const KIND_KEY: Record<string, TranslationKey> = {
  memory: 'cmpSrcMemory', graph: 'cmpSrcMemory', knowledge: 'cmpSrcDocument', lesson: 'cmpSrcLesson', mission: 'cmpSrcMission', deliverable: 'cmpSrcResult',
};

/**
 * "Why do you know this?" under an answer: the memories, documents and lessons that were really injected, what left the
 * computer for it, and two honest ways to act: forget a memory, or tell Aether what the right answer is (which becomes a
 * verified correction through the existing learning loop).
 */
export function Receipts({ message, t, notify }: Props) {
  const [open, setOpen] = useState(false);
  const [correcting, setCorrecting] = useState(false);
  const [text, setText] = useState('');
  const [gone, setGone] = useState<Set<string>>(new Set());
  const sources = (message.sources || []).filter(s => !gone.has(s.ref));
  const egress = message.egress;
  if (!sources.length && !egress) return null;

  const where = egress
    ? egress.local_only
      ? t('cmpEgressLocal')
      : `${t('cmpEgressCloud', { provider: egress.providers.join(', ') || '—' })}${egress.redactions_total > 0 ? ` · ${t('cmpEgressMasked', { count: egress.redactions_total })}` : ''}${egress.unmasked ? ` · ${t('cmpEgressUnmasked')}` : ''}`
    : '';

  const forget = async (s: AnswerSource) => {
    try {
      const res = await fetch(apiUrl(`/api/memories/${encodeURIComponent(s.ref)}`), { method: 'DELETE' });
      if (!res.ok) throw new Error(String(res.status));
      setGone(prev => new Set(prev).add(s.ref));
      notify(t('cmpForgotten'), 'success');
    } catch {
      notify(t('cmpForgetFailed'), 'error');
    }
  };

  const sendCorrection = async () => {
    const correction = text.trim();
    if (!correction) return;
    try {
      const res = await fetch(apiUrl('/api/learning/corrections'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          problem: message.content.slice(0, 600),
          correction,
          rationale: 'Correction given by the user from the answer receipts',
          evidence: { message_id: message.id, sources: sources.map(s => ({ kind: s.kind, ref: s.ref })) },
        }),
      });
      if (!res.ok) throw new Error(String(res.status));
      const saved = await res.json();
      // The user is the authority on their own correction: verify it so it can become a lesson.
      await fetch(apiUrl(`/api/learning/corrections/${encodeURIComponent(saved.id)}/verify`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ evidence: { source: 'user', message_id: message.id } }),
      }).catch(() => undefined);
      setText('');
      setCorrecting(false);
      notify(t('cmpCorrectionSaved'), 'success');
    } catch {
      notify(t('cmpCorrectionFailed'), 'error');
    }
  };

  const summary = [sources.length ? t('cmpSources', { count: sources.length }) : '', where].filter(Boolean).join(' · ');

  return (
    <div className="cmp-receipts" data-testid="companion-receipts">
      <button className="cmp-receipts-toggle" onClick={() => setOpen(o => !o)} aria-expanded={open} data-testid="companion-receipts-toggle">{summary}</button>
      {open && (
        <div className="cmp-receipts-body">
          {sources.map(s => (
            <div className="cmp-source" key={`${s.kind}-${s.ref}`} data-testid="companion-source">
              <span className="cmp-source-kind">{KIND_KEY[s.kind] ? t(KIND_KEY[s.kind]) : s.kind}</span>
              <span className="cmp-source-title">{s.title || s.source || s.ref}</span>
              {s.forgettable && <button className="cmp-link" onClick={() => forget(s)} data-testid="companion-forget">{t('cmpForget')}</button>}
            </div>
          ))}
          {!correcting ? (
            <button className="cmp-link" onClick={() => setCorrecting(true)} data-testid="companion-not-correct">{t('cmpNotCorrect')}</button>
          ) : (
            <div className="cmp-correct">
              <textarea rows={2} autoFocus value={text} placeholder={t('cmpCorrectionPlaceholder')} onChange={e => setText(e.target.value)} data-testid="companion-correction-input" />
              <div className="cmp-row">
                <button className="cmp-btn" onClick={() => { setCorrecting(false); setText(''); }}>{t('cmpDismiss')}</button>
                <button className="cmp-btn primary" disabled={!text.trim()} onClick={sendCorrection} data-testid="companion-correction-send">{t('cmpCorrectionSend')}</button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
