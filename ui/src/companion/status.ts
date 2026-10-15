/**
 * Companion status model. Every status is derived from facts the runtime or the browser actually reported;
 * nothing is simulated. "listening" is only reachable while the speech engine has really started.
 */
import type { OrbState } from '../orb/OrbEngine';

export type CompanionStatus =
  | 'available'
  | 'listening'
  | 'processing'
  | 'awaiting_approval'
  | 'error'
  | 'completed';

export interface StatusFacts {
  /** The browser speech engine reported that it started and has not ended. */
  listening: boolean;
  /** A chat request is in flight. */
  submitting: boolean;
  /** Approvals the runtime reports as pending. */
  pendingApprovals: number;
  /** Background tasks / missions the runtime reports as running or pending. */
  runningTasks: number;
  /** The last request failed (runtime unreachable, provider missing, server error) and was not dismissed. */
  hasError: boolean;
  /** A response or task finished a moment ago (transient). */
  justCompleted: boolean;
}

/** Priority: the user's attention is needed > active work > failure > a brief completion > idle. */
export function deriveCompanionStatus(f: StatusFacts): CompanionStatus {
  if (f.pendingApprovals > 0) return 'awaiting_approval';
  if (f.listening) return 'listening';
  if (f.submitting || f.runningTasks > 0) return 'processing';
  if (f.hasError) return 'error';
  if (f.justCompleted) return 'completed';
  return 'available';
}

/** The orb engine has no dedicated error state: errors are drawn as a badge/ring around an idle orb. */
export function orbStateFor(status: CompanionStatus): OrbState {
  switch (status) {
    case 'listening':
      return 'listening';
    case 'processing':
      return 'working';
    case 'awaiting_approval':
      return 'needs-you';
    case 'completed':
      return 'done';
    default:
      return 'idle';
  }
}

export const STATUS_LABEL_KEYS = {
  available: 'cmpStatusAvailable',
  listening: 'cmpStatusListening',
  processing: 'cmpStatusProcessing',
  awaiting_approval: 'cmpStatusApproval',
  error: 'cmpStatusError',
  completed: 'cmpStatusCompleted',
} as const;

export const STATUS_COLORS: Record<CompanionStatus, string> = {
  available: '#8b8b98',
  listening: '#38bdf8',
  processing: '#a78bfa',
  awaiting_approval: '#f5b84b',
  error: '#f0616d',
  completed: '#4ade80',
};
