// The spoken brief when Aether opens on the orb (once a day). On by default; the text is shown anyway.
const KEY = 'aether_greet_aloud';

export function greetAloudEnabled(): boolean {
  try { return localStorage.getItem(KEY) !== '0'; } catch { return true; }
}

export function setGreetAloud(on: boolean): void {
  try { localStorage.setItem(KEY, on ? '1' : '0'); } catch { /* private window: keep the default */ }
}
