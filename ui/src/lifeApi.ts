import { apiUrl } from './api';

export interface Contact { id: string; name: string; kind: 'client' | 'person' | 'company'; company: string; email: string; phone: string; notes: string }
export interface Job { id: string; contact_id: string | null; contact_name?: string | null; title: string; status: 'open' | 'done'; due_at: number | null; notes: string }
export interface Reminder { id: string; text: string; due_at: number | null; done: boolean }
export interface TodayData {
  date: string;
  brief: string;
  empty: boolean;
  calendar_error: string;
  pending_approvals: number;
  counts: { events: number; overdue: number; today: number; upcoming: number };
  events: { title: string; start: number; location: string; all_day: boolean }[];
  jobs: { overdue: Job[]; today: Job[]; upcoming: Job[]; undated: Job[] };
  reminders: { overdue: Reminder[]; today: Reminder[]; undated: Reminder[] };
}
export type Proposal =
  | { status: 'ok'; kind: 'job' | 'reminder' | 'contact'; title: string; notes: string; due_at: number | null; contact: { id: string | null; name: string; new: boolean } | null; email: string; phone: string }
  | { status: 'empty' | 'nothing' | 'unavailable' | 'failed'; reason?: string };

// The interface language, so what Aether writes into Memory about a person or a job reads in that language
function uiLanguage(): string {
  try {
    const saved = localStorage.getItem('aether_language');
    if (saved === 'en' || saved === 'it') return saved;
  } catch { /* storage unavailable */ }
  return navigator.language.startsWith('it') ? 'it' : 'en';
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(apiUrl(path), init && { ...init, headers: { 'Content-Type': 'application/json', 'X-Aether-Language': uiLanguage(), ...(init.headers || {}) } });
  if (!res.ok) throw new Error(String(res.status));
  return res.json() as Promise<T>;
}
const body = (v: unknown) => JSON.stringify(v);

export const lifeApi = {
  today: (language: string) => call<TodayData>(`/api/life/today?language=${encodeURIComponent(language)}`),
  capture: (text: string, language: string) => call<Proposal>('/api/life/capture', { method: 'POST', body: body({ text, language }) }),
  contacts: () => call<{ items: Contact[] }>('/api/life/contacts').then(r => r.items),
  addContact: (c: Partial<Contact>) => call<Contact>('/api/life/contacts', { method: 'POST', body: body(c) }),
  updateContact: (id: string, c: Partial<Contact>) => call<Contact>(`/api/life/contacts/${encodeURIComponent(id)}`, { method: 'PATCH', body: body(c) }),
  deleteContact: (id: string) => call<{ deleted: boolean }>(`/api/life/contacts/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  jobs: (contactId?: string) => call<{ items: Job[] }>(`/api/life/jobs${contactId ? `?contact_id=${encodeURIComponent(contactId)}` : ''}`).then(r => r.items),
  addJob: (j: { title: string; contact_id?: string | null; due_at?: number | null; notes?: string; source?: string }) => call<Job>('/api/life/jobs', { method: 'POST', body: body(j) }),
  updateJob: (id: string, j: Partial<Job>) => call<Job>(`/api/life/jobs/${encodeURIComponent(id)}`, { method: 'PATCH', body: body(j) }),
  deleteJob: (id: string) => call<{ deleted: boolean }>(`/api/life/jobs/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  addReminder: (r: { text: string; due_at?: number | null; source?: string }) => call<Reminder>('/api/life/reminders', { method: 'POST', body: body(r) }),
  doneReminder: (id: string, done = true) => call<Reminder>(`/api/life/reminders/${encodeURIComponent(id)}/done?done=${done}`, { method: 'POST' }),
};

export const fmtDue = (ts: number | null | undefined, lang: string): string =>
  ts ? new Date(ts * 1000).toLocaleDateString(lang === 'it' ? 'it-IT' : 'en-US', { weekday: 'short', day: 'numeric', month: 'short' }) : '';
export const fmtTime = (ts: number, lang: string): string => new Date(ts * 1000).toLocaleTimeString(lang === 'it' ? 'it-IT' : 'en-US', { hour: '2-digit', minute: '2-digit' });
