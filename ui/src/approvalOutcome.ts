// Pure helpers (no imports) that turn the backend's approval answer into what the UI may truthfully say.
// The backend (POST /api/approvals/{id}/approve|reject) answers { success, status, message, entity } where status is one of
// approved | already_completed | in_progress | rejected | failed | not_executed. Approving never implies that the action
// succeeded: only `approved` / `already_completed` mean it finished, and a coding run that was merely started
// (entity.output_data.run_terminal === false) is not finished either.

export type ApprovalStatus =
  | 'approved'
  | 'rejected'
  | 'already_completed'
  | 'in_progress'
  | 'not_executed'
  | 'expired'
  | 'unauthorized'
  | 'failed';

export type ApprovalDecision = 'approve' | 'reject';
export type ToastKind = 'success' | 'info' | 'error';

export interface ApprovalOutcome {
  success: boolean;
  status: string;
  entity?: any;
}

export function approvalToastKind(res: ApprovalOutcome, decision: ApprovalDecision): ToastKind {
  if (!res.success) return 'error';
  switch (res.status) {
    case 'failed':
    case 'not_executed':
    case 'unauthorized':
    case 'expired':
      return 'error';
    case 'in_progress':
    case 'already_completed':
    case 'rejected':
      return 'info';
    default:
      return decision === 'reject' ? 'info' : 'success';
  }
}

/** True only when the approved action has really finished (not merely accepted, running or started). */
export function approvalIsFinished(res: ApprovalOutcome): boolean {
  if (!res.success) return false;
  if (res.status !== 'approved' && res.status !== 'already_completed') return false;
  return res.entity?.output_data?.run_terminal !== false;
}

/** True when the decision was accepted but the work is still going (running, or a coding run was only started). */
export function approvalIsInProgress(res: ApprovalOutcome): boolean {
  if (!res.success) return false;
  if (res.status === 'in_progress') return true;
  return res.status === 'approved' && res.entity?.output_data?.run_terminal === false;
}

/** Fallback text, used only if the backend sent no message. Never claims execution. */
export function defaultApprovalMessage(decision: ApprovalDecision, status: string): string {
  if (decision === 'reject') return status === 'already_completed' ? 'This review was already declined.' : 'Review declined.';
  switch (status) {
    case 'already_completed':
      return 'This review was already completed.';
    case 'in_progress':
      return 'Approval accepted; the action is still in progress.';
    case 'failed':
      return 'The action was approved but its execution failed.';
    case 'not_executed':
      return 'The action was not executed.';
    default:
      return 'Approval recorded.';
  }
}
