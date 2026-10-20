import { useCallback, useContext, useEffect, useState } from 'react';
import { ToastContext } from './toast';
import { useTranslation } from './i18n';
import { fmtDue, fmtTime, lifeApi, type Job, type Proposal, type Reminder, type TodayData } from './lifeApi';
import './life.css';

/**
 * Home "Today": what is on your calendar, what is due and overdue (jobs and reminders), what waits for your approval, and a
 * one-line capture ("Rossi vuole il preventivo entro venerdì") that shows a proposal you accept or drop. Nothing is stored
 * before you press Save.
 */
export function Today({ navigate }: { navigate: (view: string) => void }) {
  const { t, language } = useTranslation();
  const toast = useContext(ToastContext);
  const [data, setData] = useState<TodayData | null>(null);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [proposal, setProposal] = useState<Proposal | null>(null);

  const load = useCallback(async () => {
    try { setData(await lifeApi.today(language)); } catch { setData(null); }
  }, [language]);
  useEffect(() => { void load(); }, [load]);

  const capture = async () => {
    const v = text.trim();
    if (!v || busy) return;
    setBusy(true);
    try { setProposal(await lifeApi.capture(v, language)); } catch { setProposal({ status: 'failed' }); } finally { setBusy(false); }
  };

  const save = async () => {
    if (!proposal || proposal.status !== 'ok') return;
    try {
      let contactId = proposal.contact?.id ?? null;
      if (proposal.contact?.new && proposal.contact.name) contactId = (await lifeApi.addContact({ name: proposal.contact.name, kind: 'client', email: proposal.email, phone: proposal.phone })).id;
      if (proposal.kind === 'job') await lifeApi.addJob({ title: proposal.title, contact_id: contactId, due_at: proposal.due_at, notes: proposal.notes, source: 'capture' });
      else if (proposal.kind === 'reminder') await lifeApi.addReminder({ text: proposal.title, due_at: proposal.due_at, source: 'capture' });
      setProposal(null);
      setText('');
      toast(t('lifeSaved'), 'success');
      void load();
    } catch { toast(t('lifeSaveFailed'), 'error'); }
  };

  const doneJob = async (j: Job) => { await lifeApi.updateJob(j.id, { status: 'done' }).catch(() => undefined); void load(); };
  const doneRem = async (r: Reminder) => { await lifeApi.doneReminder(r.id).catch(() => undefined); void load(); };

  const jobRow = (j: Job, late = false) => (
    <li key={j.id} className={late ? 'late' : ''}>
      <button className="life-check" aria-label={t('lifeMarkDone')} onClick={() => doneJob(j)} data-testid={`today-done-${j.id}`} />
      <span className="life-main">{j.title}{j.contact_name && <small>{j.contact_name}</small>}</span>
      <time>{fmtDue(j.due_at, language)}</time>
    </li>
  );
  const remRow = (r: Reminder, late = false) => (
    <li key={r.id} className={late ? 'late' : ''}>
      <button className="life-check" aria-label={t('lifeMarkDone')} onClick={() => doneRem(r)} data-testid={`today-done-${r.id}`} />
      <span className="life-main">{r.text}</span>
      <time>{fmtDue(r.due_at, language)}</time>
    </li>
  );

  const overdue = data ? [...data.jobs.overdue.map(j => jobRow(j, true)), ...data.reminders.overdue.map(r => remRow(r, true))] : [];
  const todays = data ? [...data.jobs.today.map(j => jobRow(j)), ...data.reminders.today.map(r => remRow(r))] : [];
  const soon = data ? data.jobs.upcoming.map(j => jobRow(j)) : [];

  return (
    <section className="life-today" data-testid="today-card" aria-label={t('lifeToday')}>
      <header>
        <h2>{t('lifeToday')}</h2>
        <button className="life-link" onClick={() => navigate('people')} data-testid="today-open-people">{t('lifePeopleLink')}</button>
      </header>
      {data && !data.empty && <p className="life-brief" data-testid="today-brief">{data.brief}</p>}
      {data && data.empty && <p className="life-empty" data-testid="today-empty">{t('lifeNothing')}</p>}
      {data?.calendar_error && <p className="life-note" data-testid="today-calendar-note">{t('lifeCalendarNote')}</p>}
      {data && data.events.length > 0 && (
        <ul className="life-list" data-testid="today-events">
          {data.events.map((e, i) => <li key={i}><span className="life-dot" aria-hidden /><span className="life-main">{e.title}{e.location && <small>{e.location}</small>}</span><time>{e.all_day ? t('lifeAllDay') : fmtTime(e.start, language)}</time></li>)}
        </ul>
      )}
      {overdue.length > 0 && <><h3 className="late">{t('lifeOverdue')}</h3><ul className="life-list" data-testid="today-overdue">{overdue}</ul></>}
      {todays.length > 0 && <><h3>{t('lifeDueToday')}</h3><ul className="life-list" data-testid="today-due">{todays}</ul></>}
      {soon.length > 0 && <><h3>{t('lifeSoon')}</h3><ul className="life-list" data-testid="today-soon">{soon}</ul></>}
      {data && data.pending_approvals > 0 && <button className="life-link" onClick={() => navigate('home')} data-testid="today-approvals">{t('lifeApprovals', { count: data.pending_approvals })}</button>}

      <div className="life-capture">
        <input aria-label={t('lifeCapturePlaceholder')} placeholder={t('lifeCapturePlaceholder')} value={text} onChange={e => setText(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') void capture(); }} data-testid="today-capture-input" />
        <button className="btn btn-secondary" disabled={busy || !text.trim()} onClick={capture} data-testid="today-capture-btn">{busy ? t('lifeCapturing') : t('lifeAdd')}</button>
      </div>
      {proposal && proposal.status === 'ok' && (
        <div className="life-proposal" data-testid="today-proposal">
          <b>{proposal.kind === 'job' ? t('lifeKindJob') : proposal.kind === 'reminder' ? t('lifeKindReminder') : t('lifeKindContact')}: {proposal.title || proposal.contact?.name}</b>
          <small>{[proposal.contact ? `${proposal.contact.name}${proposal.contact.new ? ` (${t('lifeNewContact')})` : ''}` : '', proposal.due_at ? fmtDue(proposal.due_at, language) : t('lifeNoDate')].filter(Boolean).join(' · ')}</small>
          <div className="life-actions"><button className="life-link" onClick={() => setProposal(null)}>{t('lifeDrop')}</button><button className="btn btn-primary" onClick={save} data-testid="today-proposal-save">{t('lifeSave')}</button></div>
        </div>
      )}
      {proposal && proposal.status !== 'ok' && <p className="life-note" data-testid="today-proposal-none">{proposal.status === 'unavailable' ? t('lifeNeedModel') : proposal.status === 'failed' ? t('lifeCaptureFailed') : t('lifeNothingFound')}</p>}
    </section>
  );
}
