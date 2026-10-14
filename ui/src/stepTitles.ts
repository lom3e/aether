// Titles of the steps the backend reports while it works ("Understanding intent", ...). They are produced as fixed
// English identifiers by the server, so the UI translates the known ones and shows any other title untouched.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type T = (key: any) => string;

const EXACT: Record<string, string> = {
  'Understanding intent': 'stepUnderstandingIntent',
  'Consulting memory & knowledge': 'stepConsultingMemory',
  'Synthesizing response': 'stepSynthesizing',
  'Saving to memory': 'stepSavingMemory',
  'Querying calendar events': 'stepQueryingCalendar',
};

const PREFIX: Array<[string, string]> = [
  ['Prepared proposal: ', 'stepPreparedProposal'],
  ['Reading document: ', 'stepReadingDocument'],
];

export function translateStepTitle(title: string, t: T): string {
  if (!title) return title;
  if (EXACT[title]) return t(EXACT[title]);
  for (const [prefix, key] of PREFIX) {
    if (title.startsWith(prefix)) return `${t(key)}: ${title.slice(prefix.length)}`;
  }
  return title;
}
