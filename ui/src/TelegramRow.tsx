import { useCallback, useContext, useEffect, useState } from 'react';
import { apiUrl } from './api';
import { openExternalUrl } from './desktop';
import { ToastContext } from './toast';
import { useTranslation } from './i18n';

interface MobileStatus { configured: boolean; bot_username?: string; paired?: { chat_id: string; name: string }[]; running?: boolean; last_error?: string }

/** Aether on the phone: create a bot once (BotFather), then pair your chat with a one-time link. */
export function TelegramRow() {
  const { t } = useTranslation();
  const toast = useContext(ToastContext);
  const [st, setSt] = useState<MobileStatus>({ configured: false });
  const [open, setOpen] = useState(false);
  const [token, setToken] = useState('');
  const [busy, setBusy] = useState(false);
  const [link, setLink] = useState('');
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      const res = await fetch(apiUrl('/api/connections/telegram/mobile'));
      if (res.ok) setSt(await res.json());
    } catch { /* offline: keep the last state */ }
  }, []);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    if (!link) return;
    const id = window.setInterval(load, 3000); // the pairing happens on the phone: notice it here
    return () => window.clearInterval(id);
  }, [link, load]);

  const setup = async () => {
    if (!token.trim() || busy) return;
    setBusy(true); setError('');
    try {
      const res = await fetch(apiUrl('/api/connections/telegram/mobile/setup'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ bot_token: token.trim() }) });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) { setError(t('tgInvalidToken')); return; }
      setToken(''); setLink(data.link || ''); void load();
    } finally {
      setBusy(false);
    }
  };
  const newLink = async () => {
    const res = await fetch(apiUrl('/api/connections/telegram/mobile/pairing'), { method: 'POST' });
    if (res.ok) setLink((await res.json()).link || '');
  };
  const unpair = async () => {
    await fetch(apiUrl('/api/connections/telegram/mobile/pairing'), { method: 'DELETE' });
    toast(t('tgUnpaired'), 'success'); setLink(''); void load();
  };

  const paired = st.paired || [];
  const state = paired.length ? 'connected' : st.configured ? 'waiting' : 'none';

  return (
    <li data-testid="conn-row-telegram" data-state={state} className="cn-tg">
      <span className={`cn-dot ${paired.length ? 'on' : ''}`} aria-hidden />
      <span className="cn-main">
        <b>Telegram</b>
        <small>
          {paired.length ? t('tgPairedWith', { names: paired.map(p => p.name || p.chat_id).join(', ') })
            : st.configured ? t('tgBotReady', { bot: st.bot_username || '' }) : t('tgDesc')}
        </small>
        {(open || link) && !paired.length && (
          <span className="cn-tg-steps">
            {!st.configured ? (
              <>
                <ol>
                  <li>{t('tgStep1')} <button className="cn-link" onClick={() => openExternalUrl('https://t.me/BotFather')}>@BotFather</button></li>
                  <li>{t('tgStep2')}</li>
                  <li>{t('tgStep3')}</li>
                </ol>
                <span className="cn-tg-form">
                  <input value={token} onChange={e => setToken(e.target.value)} placeholder="123456789:AA…" aria-label={t('tgTokenLabel')} data-testid="tg-token-input" autoComplete="off" spellCheck={false} />
                  <button className="btn btn-primary" disabled={!token.trim() || busy} onClick={setup} data-testid="tg-setup-btn">{busy ? t('tgChecking') : t('cnConnect')}</button>
                </span>
              </>
            ) : link ? (
              <>
                <span>{t('tgOpenOnPhone')}</span>
                <span className="cn-code"><code data-testid="tg-link">{link}</code>
                  <button className="cn-link" onClick={() => navigator.clipboard?.writeText(link)}>{t('cnCopy')}</button>
                  <button className="cn-link" onClick={() => openExternalUrl(link)}>{t('tgOpen')}</button></span>
                <small>{t('tgLinkHint')}</small>
              </>
            ) : null}
          </span>
        )}
        {error && <span className="cn-error" role="alert">{error}</span>}
      </span>
      {paired.length ? <button className="cn-link" onClick={unpair} data-testid="tg-unpair">{t('cnDisconnect')}</button>
        : st.configured ? <button className="btn btn-primary" onClick={newLink} data-testid="tg-new-link">{t('tgPairPhone')}</button>
        : <button className="btn btn-primary" onClick={() => setOpen(o => !o)} data-testid="tg-open">{t('cnSetUp')}</button>}
    </li>
  );
}
