// Spoken answers with the voices already on this computer (Web Speech API): offline, free, nothing to download.
// Reads the answer as written, without Markdown symbols, in the language of the interface.

const STORE_KEY = 'aether_speak_voice_answers';

export function speakVoiceAnswersEnabled(): boolean {
  try {
    return localStorage.getItem(STORE_KEY) !== '0'; // on by default: if you ask by voice, you are answered by voice
  } catch {
    return true;
  }
}

export function setSpeakVoiceAnswers(on: boolean): void {
  try {
    localStorage.setItem(STORE_KEY, on ? '1' : '0');
  } catch { /* private window: keep the default */ }
}

export function speakable(markdown: string): string {
  return (markdown || '')
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/`([^`]*)`/g, '$1')
    .replace(/!\[[^\]]*\]\([^)]*\)/g, ' ')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/^#{1,6}\s*/gm, '')
    .replace(/\*\*|__|\*|_/g, '')
    .replace(/^\s*[-•]\s+/gm, '')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 1200);
}

function pickVoice(lang: string): SpeechSynthesisVoice | undefined {
  const voices = window.speechSynthesis?.getVoices?.() || [];
  const prefix = lang === 'it' ? 'it' : 'en';
  const own = voices.filter(v => v.lang?.toLowerCase().startsWith(prefix));
  return own.find(v => /premium|enhanced|siri/i.test(v.name)) || own.find(v => v.localService) || own[0];
}

export function canSpeak(): boolean {
  return typeof window !== 'undefined' && 'speechSynthesis' in window;
}

export function stopSpeaking(): void {
  try {
    if (canSpeak()) window.speechSynthesis.cancel();
  } catch { /* nothing to stop */ }
}

export function speak(text: string, lang: string, onEnd?: () => void): boolean {
  if (!canSpeak()) return false;
  const clean = speakable(text);
  if (!clean) return false;
  try { // a voice engine error must never take the interface down with it
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(clean);
    u.lang = lang === 'it' ? 'it-IT' : 'en-US';
    const voice = pickVoice(lang);
    if (voice) u.voice = voice;
    u.rate = 1.03;
    u.onend = () => onEnd?.();
    u.onerror = () => onEnd?.();
    window.speechSynthesis.speak(u);
    return true;
  } catch {
    onEnd?.();
    return false;
  }
}
