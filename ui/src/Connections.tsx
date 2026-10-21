import { useCallback, useContext, useEffect, useRef, useState } from 'react';
import { Link2 } from 'lucide-react';
import { apiUrl } from './api';
import { openExternalUrl, showMainWindow } from './desktop';
import { ToastContext } from './toast';
import { useTranslation, type TranslationKey } from './i18n';
import { TopHeader } from './TopHeader';
import { ConnectionsAdvanced } from './ConnectionsAdvanced';
import './connections.css';

interface ConnectionsProps {
  navigate?: (view: string, params?: any) => void;
  initialExecutionId?: string | null;
  initialTab?: 'apps' | 'calendar' | 'actions';
}

interface Conn { provider: string; status: string; account_name?: string }
interface ProviderStatus { has_client_id?: boolean; ready_for_user_connect?: boolean }
interface FlowStatus { status: 'pending' | 'success' | 'error' | 'expired' | 'cancelled'; account?: string; error?: string }

const ROWS: { id: string; name: string; desc: TranslationKey; device?: boolean }[] = [
  { id: 'google_calendar', name: 'Google Calendar', desc: 'cnCalendarDesc' },
  { id: 'github', name: 'GitHub', desc: 'cnGithubDesc', device: true },
  { id: 'slack', name: 'Slack', desc: 'cnSlackDesc' },
  { id: 'notion', name: 'Notion', desc: 'cnNotionDesc' },
];

/**
 * Connections, calmly: one row per service and one button. Google and GitHub connect with a browser click (no keys to paste);
 * everything that still needs a key, a bot or a custom API lives under "Advanced" (the full previous screen).
 */
export function Connections({ navigate, initialExecutionId, initialTab }: ConnectionsProps) {
  const { t } = useTranslation();
  const toast = useContext(ToastContext);
  const [conns, setConns] = useState<Conn[]>([]);
  const [providers, setProviders] = useState<Record<string, ProviderStatus>>({});
  const [flow, setFlow] = useState<{ provider: string; state: string; code?: string; uri?: string } | null>(null);
  const [error, setError] = useState<{ provider: string; text: string } | null>(null);
  const [advanced, setAdvanced] = useState(false);
  const timer = useRef<number | null>(null);

  const load = useCallback(async () => {
    try {
      const [c, p] = await Promise.all([
        fetch(apiUrl('/api/connections')).then(r => (r.ok ? r.json() : [])),
        fetch(apiUrl('/api/connections/oauth/providers')).then(r => (r.ok ? r.json() : {})),
      ]);
      setConns(Array.isArray(c) ? c : []);
      setProviders(p || {});
    } catch { /* keep what is shown */ }
  }, []);
  useEffect(() => { void load(); return () => { if (timer.current) window.clearInterval(timer.current); }; }, [load]);

  const stopPolling = () => { if (timer.current) { window.clearInterval(timer.current); timer.current = null; } };
  const reason = (e: string): TranslationKey =>
    e.startsWith('denied') ? 'cnErrDenied' : e.startsWith('exchange_failed') ? 'cnErrExchange' : e.startsWith('verification_failed') ? 'cnErrVerify' : e === 'expired' ? 'cnErrExpired' : 'cnErrGeneric';

  const poll = (provider: string, state: string) => {
    stopPolling();
    timer.current = window.setInterval(async () => {
      try {
        const res = await fetch(apiUrl(`/api/connections/oauth/flows/${encodeURIComponent(state)}`));
        if (res.status === 404) { stopPolling(); setFlow(null); return; }
        const st: FlowStatus = await res.json();
        if (st.status === 'pending') return;
        stopPolling();
        setFlow(null);
        void showMainWindow(); // the browser tab did the approval: bring Aether back to the front
        if (st.status === 'success') { toast(t('cnConnectedToast', { account: st.account || '' }), 'success'); }
        else if (st.status === 'error' || st.status === 'expired') setError({ provider, text: t(reason(st.status === 'expired' ? 'expired' : st.error || '')) });
        void load();
      } catch { /* try again on the next tick */ }
    }, 1200);
  };

  const connect = async (row: (typeof ROWS)[number]) => {
    setError(null);
    try {
      if (row.device) {
        const res = await fetch(apiUrl('/api/connections/github/oauth/device'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
        if (!res.ok) throw new Error(String(res.status));
        const d = await res.json();
        setFlow({ provider: row.id, state: d.state, code: d.user_code, uri: d.verification_uri });
        poll(row.id, d.state);
      } else {
        const res = await fetch(apiUrl(`/api/connections/${row.id}/oauth/flow`), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
        if (!res.ok) throw new Error(String(res.status));
        const d = await res.json();
        setFlow({ provider: row.id, state: d.state });
        poll(row.id, d.state);
        await openExternalUrl(d.auth_url);
      }
    } catch { setError({ provider: row.id, text: t('cnErrGeneric') }); }
  };

  const cancel = async () => {
    if (!flow) return;
    stopPolling();
    await fetch(apiUrl(`/api/connections/oauth/flows/${encodeURIComponent(flow.state)}`), { method: 'DELETE' }).catch(() => undefined);
    setFlow(null);
  };

  const disconnect = async (id: string) => {
    await fetch(apiUrl(`/api/connections/${id}/disconnect`), { method: 'POST' }).catch(() => undefined);
    void load();
  };

  // Deep links (a notification about an action, a requested tab) open the full screen.
  if (initialExecutionId || initialTab) return <ConnectionsAdvanced navigate={navigate} initialExecutionId={initialExecutionId} initialTab={initialTab} />;

  const stateOf = (id: string) => {
    const c = conns.find(x => x.provider === id);
    if (c?.status === 'verified') return { kind: 'connected' as const, account: c.account_name || '' };
    if (c && (c.status === 'verification_required' || c.status === 'verification_failed')) return { kind: 'reconnect' as const, account: '' };
    return { kind: 'none' as const, account: '' };
  };
  const available = (row: (typeof ROWS)[number]) => (row.device ? !!providers[row.id]?.has_client_id : !!providers[row.id]?.ready_for_user_connect);

  return (
    <div className="cn-page" data-testid="connections-view">
      <TopHeader title={t('cnTitle')} subtitle={t('cnSub')} icon={Link2} />
      <div className="cn-body">
        <ul className="cn-list">
          {ROWS.map(row => {
            const s = stateOf(row.id);
            const waiting = flow?.provider === row.id;
            const ok = available(row);
            return (
              <li key={row.id} data-testid={`conn-row-${row.id}`} data-state={waiting ? 'waiting' : s.kind}>
                <span className={`cn-dot ${s.kind === 'connected' ? 'on' : s.kind === 'reconnect' ? 'warn' : ''}`} aria-hidden />
                <span className="cn-main">
                  <b>{row.name}</b>
                  <small>
                    {waiting ? (flow?.code ? t('cnGithubCode') : t('cnWaiting'))
                      : s.kind === 'connected' ? t('cnConnectedAs', { account: s.account })
                      : s.kind === 'reconnect' ? t('cnNeedsReconnect')
                      : ok ? t(row.desc) : t('cnNotAvailable')}
                  </small>
                  {waiting && flow?.code && (
                    <span className="cn-code" data-testid="cn-device-code">
                      <code>{flow.code}</code>
                      <button className="cn-link" onClick={() => navigator.clipboard?.writeText(flow.code || '')}>{t('cnCopy')}</button>
                      <button className="cn-link" onClick={() => openExternalUrl(flow.uri || 'https://github.com/login/device')}>{t('cnOpenGithub')}</button>
                    </span>
                  )}
                  {error?.provider === row.id && <span className="cn-error" role="alert" data-testid={`conn-error-${row.id}`}>{error.text}</span>}
                </span>
                {waiting ? <button className="btn btn-secondary" onClick={cancel} data-testid={`conn-cancel-${row.id}`}>{t('cnCancel')}</button>
                  : s.kind === 'connected' ? <button className="cn-link" onClick={() => disconnect(row.id)} data-testid={`conn-disconnect-${row.id}`}>{t('cnDisconnect')}</button>
                  : ok ? <button className="btn btn-primary" onClick={() => connect(row)} data-testid={`conn-connect-${row.id}`}>{s.kind === 'reconnect' ? t('cnReconnect') : t('cnConnect')}</button>
                  : <button className="cn-link" onClick={() => setAdvanced(true)} data-testid={`conn-setup-${row.id}`}>{t('cnSetUp')}</button>}
              </li>
            );
          })}
        </ul>

        <div className="cn-advanced">
          <button className="cn-link" aria-expanded={advanced} onClick={() => setAdvanced(a => !a)} data-testid="connections-advanced-toggle">{t('cnAdvanced')}</button>
          <p>{t('cnAdvancedHint')}</p>
          {advanced && <div className="cn-advanced-body" data-testid="connections-advanced"><ConnectionsAdvanced navigate={navigate} /></div>}
        </div>
      </div>
    </div>
  );
}
