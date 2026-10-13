/**
 * How a coding run is shown. The action record "succeeds" when the request is accepted; the RUN may still be going,
 * waiting for the user, rejected by verification or in need of rework. Only a completed run whose independent
 * verification passed is shown as a success: everything else says what it really is.
 */
export type CodingKind = 'active' | 'waiting' | 'completed' | 'unverified' | 'needs_review' | 'failed';

export interface CodingResultLike {
  status?: string | null;
  awaiting?: string | null;
  run_terminal?: boolean | null;
  verified?: boolean | null;
  deliverable_ready?: boolean | null;
  verification_passed?: boolean | null;
}

export interface CodingPresentation {
  kind: CodingKind;
  label: string;          // pill text
  pillClass: string;      // css class of the pill
  title: string;          // card headline
  workStatus: 'working' | 'needs-you' | 'done';
  verified: boolean;
}

const WAITING = new Set(['waiting_for_interaction', 'waiting_for_approval']);
const ACTIVE = new Set(['queued', 'running', 'in_progress']);
const FAILED = new Set(['failed', 'timed_out', 'cancelled']);

export function classifyCodingResult(cr: CodingResultLike | null | undefined): CodingPresentation {
  const status = String(cr?.status ?? '').toLowerCase();
  const awaiting = cr?.awaiting ?? null;

  if (FAILED.has(status)) {
    return { kind: 'failed', label: status.replace(/_/g, ' ').toUpperCase(), pillClass: 'status-failed',
      title: 'Attività Coding Non Riuscita', workStatus: 'needs-you', verified: false };
  }
  if (status === 'requires_rework') {
    return { kind: 'needs_review', label: 'DA RIVEDERE', pillClass: 'status-review',
      title: 'Attività Coding da Rivedere', workStatus: 'needs-you', verified: false };
  }
  if (WAITING.has(status) || awaiting) {
    const approval = status === 'waiting_for_approval' || awaiting === 'approval';
    return { kind: 'waiting', label: approval ? 'IN ATTESA DI APPROVAZIONE' : 'IN ATTESA DI RISPOSTA', pillClass: 'status-waiting',
      title: approval ? 'Approvazione Richiesta' : 'Intervento Richiesto dal Coding Agent', workStatus: 'needs-you', verified: false };
  }
  if (ACTIVE.has(status) || cr?.run_terminal === false) {
    return { kind: 'active', label: 'IN CORSO', pillClass: 'status-running',
      title: 'Attività Coding in Corso', workStatus: 'working', verified: false };
  }
  if (status === 'completed') {
    const verified = cr?.verified === true || cr?.deliverable_ready === true || cr?.verification_passed === true;
    return verified
      ? { kind: 'completed', label: 'COMPLETATO • VERIFICATO', pillClass: 'status-completed',
          title: 'Attività Coding Completata e Verificata', workStatus: 'done', verified: true }
      : { kind: 'unverified', label: 'TERMINATO • NON VERIFICATO', pillClass: 'status-unverified',
          title: 'Attività Coding Terminata (Non Verificata)', workStatus: 'needs-you', verified: false };
  }
  // Unknown or missing state: never claim success.
  return { kind: 'active', label: status ? status.replace(/_/g, ' ').toUpperCase() : 'STATO SCONOSCIUTO', pillClass: 'status-running',
    title: 'Attività Coding', workStatus: 'working', verified: false };
}

/** Test output is shown as passed/failed only when the run said so; an absent result is neutral. */
export function testOutcome(testPassed: boolean | null | undefined): 'passed' | 'failed' | 'unknown' {
  return testPassed === true ? 'passed' : testPassed === false ? 'failed' : 'unknown';
}

/** Should the UI keep polling an action whose record already "succeeded"? Only while the run is genuinely active. */
export function runStillActive(out: CodingResultLike | null | undefined): boolean {
  return classifyCodingResult(out).kind === 'active';
}
