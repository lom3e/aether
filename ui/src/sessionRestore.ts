/**
 * What to do with the stored active-session id after asking the backend for that session.
 * Only a 404 proves the id is stale (the session does not exist any more). Anything else (network error, 5xx, 401,
 * 429...) is transient or unrelated: the stored id and the user's session must be kept.
 */
export type RestoreOutcome = 'restored' | 'stale' | 'keep';

export function classifyRestoreResponse(status: number | null | undefined): RestoreOutcome {
  if (status === undefined || status === null) return 'keep';   // no HTTP answer: network failure
  if (status >= 200 && status < 300) return 'restored';
  return status === 404 ? 'stale' : 'keep';
}

export const ACTIVE_SESSION_KEY = 'aether_active_session_id';

/** Removes the stored id, but only if it is still the one that turned out to be stale (never a newer one). */
export function forgetStaleSession(storage: Pick<Storage, 'getItem' | 'removeItem'>, staleId: string): boolean {
  if (storage.getItem(ACTIVE_SESSION_KEY) !== staleId) return false;
  storage.removeItem(ACTIVE_SESSION_KEY);
  return true;
}
