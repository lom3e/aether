import { useCallback, useContext, useEffect, useState } from 'react';
import { Users } from 'lucide-react';
import { ToastContext } from './toast';
import { useTranslation } from './i18n';
import { TopHeader } from './TopHeader';
import { fmtDue, lifeApi, type Contact, type Job } from './lifeApi';
import './life.css';

/** People & clients with their jobs. Everything is stored locally and mirrored into what Aether remembers; deleting forgets both. */
export function People() {
  const { t, language } = useTranslation();
  const toast = useContext(ToastContext);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [draft, setDraft] = useState<Contact | null>(null);
  const [newName, setNewName] = useState('');
  const [newKind, setNewKind] = useState<'client' | 'person'>('client');
  const [jobTitle, setJobTitle] = useState('');
  const [jobDue, setJobDue] = useState('');

  const load = useCallback(async () => {
    try {
      const [c, j] = await Promise.all([lifeApi.contacts(), lifeApi.jobs()]);
      setContacts(c);
      setJobs(j);
    } catch { /* the list stays as it was */ }
  }, []);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => { setDraft(contacts.find(c => c.id === selected) ?? null); }, [selected, contacts]);

  const mine = jobs.filter(j => j.contact_id === selected);
  const openCount = (id: string) => jobs.filter(j => j.contact_id === id && j.status === 'open').length;

  const addContact = async () => {
    if (!newName.trim()) return;
    try {
      const c = await lifeApi.addContact({ name: newName.trim(), kind: newKind });
      setNewName('');
      await load();
      setSelected(c.id);
    } catch { toast(t('lifeSaveFailed'), 'error'); }
  };
  const saveContact = async () => {
    if (!draft) return;
    try {
      await lifeApi.updateContact(draft.id, { name: draft.name, kind: draft.kind, company: draft.company, email: draft.email, phone: draft.phone, notes: draft.notes });
      toast(t('lifeSaved'), 'success');
      void load();
    } catch { toast(t('lifeSaveFailed'), 'error'); }
  };
  const forgetContact = async () => {
    if (!draft) return;
    await lifeApi.deleteContact(draft.id).catch(() => undefined);
    setSelected(null);
    toast(t('lifeForgotten'), 'success');
    void load();
  };
  const addJob = async () => {
    if (!jobTitle.trim() || !selected) return;
    const due = jobDue ? new Date(`${jobDue}T09:00:00`).getTime() / 1000 : null;
    await lifeApi.addJob({ title: jobTitle.trim(), contact_id: selected, due_at: due }).catch(() => toast(t('lifeSaveFailed'), 'error'));
    setJobTitle('');
    setJobDue('');
    void load();
  };
  const toggleJob = async (j: Job) => { await lifeApi.updateJob(j.id, { status: j.status === 'open' ? 'done' : 'open' }).catch(() => undefined); void load(); };
  const dropJob = async (j: Job) => { await lifeApi.deleteJob(j.id).catch(() => undefined); void load(); };
  const set = (k: keyof Contact, v: string) => setDraft(d => (d ? { ...d, [k]: v } : d));

  const addForm = (
    <div className="people-new">
      <input aria-label={t('peopleNamePlaceholder')} placeholder={t('peopleNamePlaceholder')} value={newName} onChange={e => setNewName(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') void addContact(); }} data-testid="people-new-name" />
      <select aria-label={t('peopleKind')} value={newKind} onChange={e => setNewKind(e.target.value as 'client' | 'person')}>
        <option value="client">{t('peopleClient')}</option>
        <option value="person">{t('peoplePerson')}</option>
      </select>
      <button className="btn btn-primary" disabled={!newName.trim()} onClick={addContact} data-testid="people-add">{t('peopleAdd')}</button>
    </div>
  );

  if (contacts.length === 0) {
    return (
      <div className="people-page" data-testid="people-view">
        <TopHeader variant="page" title={t('peopleTitle')} subtitle={t('peopleSub')} />
        <div className="people-scroll">
          <div className="people-blank">
            <span className="people-blank-icon" aria-hidden><Users size={22} /></span>
            <p className="people-empty" data-testid="people-empty">{t('peopleEmpty')}</p>
            {addForm}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="people-page" data-testid="people-view">
      <TopHeader variant="page" className="wide" title={t('peopleTitle')} subtitle={t('peopleSub')} />
      <div className="people-body">
        <aside className="people-side">
          {contacts.map(c => (
            <button key={c.id} className="row" aria-current={selected === c.id} onClick={() => setSelected(c.id)} data-testid={`person-${c.id}`}>
              {c.name}
              <small>{[c.kind === 'client' ? t('peopleClient') : c.kind === 'company' ? t('peopleCompany') : t('peoplePerson'), openCount(c.id) ? (openCount(c.id) === 1 ? t('peopleOpenJob') : t('peopleOpenJobs', { count: openCount(c.id) })) : ''].filter(Boolean).join(' · ')}</small>
            </button>
          ))}
          {addForm}
        </aside>

        <section className="people-detail">
          {!draft ? <p className="people-empty">{t('peoplePick')}</p> : (
            <>
              <div className="people-grid">
                <input aria-label={t('peopleNamePlaceholder')} value={draft.name} onChange={e => set('name', e.target.value)} data-testid="person-name" />
                <input aria-label={t('peopleCompanyLabel')} placeholder={t('peopleCompanyLabel')} value={draft.company} onChange={e => set('company', e.target.value)} />
                <input aria-label="Email" placeholder="Email" value={draft.email} onChange={e => set('email', e.target.value)} />
                <input aria-label={t('peoplePhone')} placeholder={t('peoplePhone')} value={draft.phone} onChange={e => set('phone', e.target.value)} />
              </div>
              <textarea rows={3} aria-label={t('peopleNotes')} placeholder={t('peopleNotes')} value={draft.notes} onChange={e => set('notes', e.target.value)} />
              <div className="life-actions" style={{ justifyContent: 'space-between' }}>
                <button className="life-link" onClick={forgetContact} data-testid="person-forget">{t('lifeForget')}</button>
                <button className="btn btn-primary" onClick={saveContact} data-testid="person-save">{t('lifeSave')}</button>
              </div>

              <h3 style={{ fontSize: 13, fontWeight: 500, color: 'hsl(var(--muted-fg))' }}>{t('peopleJobs')}</h3>
              <ul className="life-list" data-testid="person-jobs">
                {mine.length === 0 && <li className="people-empty">{t('peopleNoJobs')}</li>}
                {mine.map(j => (
                  <li key={j.id} style={{ opacity: j.status === 'done' ? 0.55 : 1 }}>
                    <button className="life-check" aria-label={t('lifeMarkDone')} aria-pressed={j.status === 'done'} onClick={() => toggleJob(j)} style={j.status === 'done' ? { background: 'hsl(var(--primary))', borderColor: 'hsl(var(--primary))' } : undefined} />
                    <span className="life-main" style={{ textDecoration: j.status === 'done' ? 'line-through' : 'none' }}>{j.title}</span>
                    <time>{fmtDue(j.due_at, language)}</time>
                    <button className="life-link" onClick={() => dropJob(j)}>{t('lifeForget')}</button>
                  </li>
                ))}
              </ul>
              <div className="life-capture">
                <input aria-label={t('peopleJobPlaceholder')} placeholder={t('peopleJobPlaceholder')} value={jobTitle} onChange={e => setJobTitle(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') void addJob(); }} data-testid="person-job-title" />
                <input type="date" aria-label={t('peopleDue')} value={jobDue} onChange={e => setJobDue(e.target.value)} style={{ flex: '0 0 150px' }} data-testid="person-job-due" />
                <button className="btn btn-secondary" disabled={!jobTitle.trim()} onClick={addJob} data-testid="person-job-add">{t('lifeAdd')}</button>
              </div>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
