// The runtime writes activity titles in English ("Completed: List Calendar Events"). This turns the known shapes into
// Italian for display; anything unknown is shown unchanged rather than guessed.
const PREFIX_IT: Array<[string, string]> = [
  ['Auto-approved & Executed: ', 'Eseguita automaticamente: '],
  ['Verification Failed: ', 'Verifica non riuscita: '],
  ['Quality Gate Signoff Required: ', 'Serve la tua revisione: '],
  ['Approval needed: ', 'Serve la tua approvazione: '],
  ['Prepared proposal: ', 'Proposta preparata: '],
  ['Preparing action: ', 'Preparo l\'azione: '],
  ['Mission Completed: ', 'Lavoro completato: '],
  ['Mission Failed: ', 'Lavoro non riuscito: '],
  ['Task Completed: ', 'Attività completata: '],
  ['Task Failed: ', 'Attività non riuscita: '],
  ['Reading document: ', 'Lettura documento: '],
  ['Setup Required: ', 'Da configurare: '],
  ['File Ingested: ', 'File aggiunto alla conoscenza: '],
  ['Webhook Received: ', 'Evento ricevuto: '],
  ['Personal Request: ', 'Richiesta: '],
  ['Completed: ', 'Completata: '],
  ['Verified: ', 'Collegamento verificato: '],
  ['Started: ', 'Avviata: '],
  ['Failed: ', 'Non riuscita: '],
  ['Mission: ', 'Lavoro: '],
];

const ACTION_IT: Record<string, string> = {
  'Create Calendar Event': 'Crea evento nel calendario',
  'Create Google Calendar Event': 'Crea evento in Google Calendar',
  'Update Google Calendar Event': 'Sposta evento in Google Calendar',
  'Delete Google Calendar Event': 'Cancella evento da Google Calendar',
  'List Calendar Events': 'Lettura del calendario',
  'Create Document': 'Crea documento',
  'Read Document': 'Leggi documento',
  'Web Search': 'Ricerca sul web',
  'Send Email': 'Invia email',
  'Send Slack Message': 'Invia messaggio Slack',
  'Send Telegram Message': 'Invia messaggio Telegram',
  'Search Knowledge Base': 'Cerca nella conoscenza',
  'Ingest URL into Knowledge': 'Aggiungi pagina web alla conoscenza',
  'Ingest Local File into Knowledge': 'Aggiungi file alla conoscenza',
  'Create Automation Proposal': 'Proposta di automazione',
  'Activate Automation': 'Attiva automazione',
  'Mission Dry Run': 'Anteprima del lavoro',
  'Synchronize Connections': 'Sincronizza collegamenti',
  'Delegate Coding Task': 'Affida un lavoro di codice',
  'Install Marketplace Package': 'Installa pacchetto',
  'Uninstall Marketplace Package': 'Rimuovi pacchetto',
  'Repurpose Content': 'Riadatta contenuti',
  'Calendar': 'Calendario',
  'Google_calendar': 'Google Calendar',
  'Github': 'GitHub',
};

const DESC_IT: Array<[RegExp, (m: RegExpMatchArray) => string]> = [
  [/^Successfully executed '(.+)'\.$/, m => `Eseguita: ${ACTION_IT[m[1]] || m[1]}.`],
  [/^Successfully verified (.+?) \((.+)\)\.$/, m => `Verificato ${m[1]} (${m[2]}).`],
];

export function localizeActivity(text: string | undefined | null, language: string): string {
  const s = String(text ?? '');
  if (language !== 'it' || !s) return s;
  for (const [re, fn] of DESC_IT) {
    const m = s.match(re);
    if (m) return fn(m);
  }
  for (const [en, it] of PREFIX_IT) {
    if (s.startsWith(en)) {
      const rest = s.slice(en.length);
      return it + (ACTION_IT[rest] || rest);
    }
  }
  return ACTION_IT[s] || s;
}
