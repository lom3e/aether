// Aether's ears and voice in the app.
// Hearing: the microphone is recorded while you talk and transcribed by Whisper with your provider key (much more accurate
// than the Mac's dictation, above all in Italian); without a key it falls back to the Mac's dictation. Speaking: audio made by
// the sidecar (Aether's natural voice once downloaded, else the best voice on this Mac, or OpenAI's if chosen), with the Web
// Speech voices as the last fallback.
// Both feed a level bus the orb listens to, so it moves with your voice and with its own.
import { apiUrl } from '../api';

// -- level bus (0..1) -------------------------------------------------------------------------------------------------------
type LevelFn = (level: number) => void;
const levelSubs = new Set<LevelFn>();
export function onVoiceLevel(fn: LevelFn): () => void {
  levelSubs.add(fn);
  return () => { levelSubs.delete(fn); };
}
function emitLevel(level: number) { levelSubs.forEach(fn => fn(level)); }

let ctx: AudioContext | null = null;
function audioContext(): AudioContext | null {
  try {
    const C = window.AudioContext || (window as any).webkitAudioContext;
    if (!C) return null;
    ctx = ctx || new C();
    if (ctx.state === 'suspended') void ctx.resume().catch(() => undefined);
    return ctx;
  } catch { return null; }
}

/** Reads the loudness of `source` every frame; returns a stop function. `onFrame` gets the level too (silence detection). */
function meter(source: AudioNode, ac: AudioContext, onFrame?: (level: number) => void): () => void {
  const an = ac.createAnalyser();
  an.fftSize = 512;
  source.connect(an);
  const buf = new Uint8Array(an.fftSize);
  let raf = 0;
  let smooth = 0;
  const tick = () => {
    an.getByteTimeDomainData(buf);
    let sum = 0;
    for (let i = 0; i < buf.length; i++) { const v = (buf[i] - 128) / 128; sum += v * v; }
    const level = Math.min(1, Math.sqrt(sum / buf.length) * 4.2);
    smooth = smooth * 0.6 + level * 0.4;
    emitLevel(smooth);
    onFrame?.(level);
    raf = requestAnimationFrame(tick);
  };
  raf = requestAnimationFrame(tick);
  return () => { cancelAnimationFrame(raf); try { source.disconnect(an); } catch { /* gone */ } emitLevel(0); };
}

// -- status ---------------------------------------------------------------------------------------------------------------
export interface NaturalVoice {
  state: 'ready' | 'missing' | 'downloading' | 'unavailable';
  voices: { id: string; name: string }[];
  download: { state: string; done: number; total: number; error: string };
  size_mb: number;
}
export interface VoiceStatus {
  settings: { stt: string; tts: string; system_voice: string; openai_voice: string; neural_voice: string };
  stt: { engine: 'device' | 'groq' | 'openai'; available: string[]; model: string };
  tts: { engine: 'neural' | 'system' | 'openai' | 'device'; available: string[]; voice: string; quality: string; voices: { name: string; quality: string }[]; openai_voices: string[]; needs_better_voice: boolean; neural?: NaturalVoice };
}
let statusCache: { lang: string; p: Promise<VoiceStatus | null> } | null = null;
export function voiceStatus(lang: string, refresh = false): Promise<VoiceStatus | null> {
  if (!refresh && statusCache && statusCache.lang === lang) return statusCache.p;
  const p = fetch(apiUrl(`/api/voice/status?language=${encodeURIComponent(lang)}`)).then(r => (r.ok ? r.json() : null)).catch(() => null);
  statusCache = { lang, p };
  return p;
}
export function forgetVoiceStatus() { statusCache = null; }

// -- hearing --------------------------------------------------------------------------------------------------------------
export interface ListenCallbacks {
  onText: (text: string) => void;
  onListening: (on: boolean) => void;
  onTranscribing?: (on: boolean) => void;
  onError?: (code: string) => void;
}
export interface Listener { start: (opts?: { autoStop?: boolean }) => Promise<void>; stop: () => void; abort: () => void; active: () => boolean }

const deviceCtor = () => (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
export function canListen(): boolean {
  return !!deviceCtor() || (!!navigator.mediaDevices?.getUserMedia && typeof (window as any).MediaRecorder !== 'undefined');
}

export function createListener(language: string, cb: ListenCallbacks): Listener {
  let rec: MediaRecorder | null = null;
  let dict: any = null;
  let stream: MediaStream | null = null;
  let stopMeter: (() => void) | null = null;
  let aborted = false;
  let startedAt = 0;
  let on = false;

  const release = () => {
    stopMeter?.(); stopMeter = null;
    stream?.getTracks().forEach(t => t.stop()); stream = null;
  };

  const startDevice = () => {
    const C = deviceCtor();
    if (!C) { cb.onError?.('unsupported'); return; }
    dict = new C();
    dict.continuous = false;
    dict.interimResults = true;
    dict.lang = language === 'it' ? 'it-IT' : 'en-US';
    dict.onstart = () => { on = true; cb.onListening(true); };
    dict.onresult = (e: any) => {
      let text = '';
      for (let i = e.resultIndex; i < e.results.length; i++) text += e.results[i][0].transcript;
      if (text) cb.onText(text);
    };
    dict.onerror = (e: any) => { cb.onError?.(e?.error || 'error'); };
    dict.onend = () => { on = false; dict = null; cb.onListening(false); };
    try { dict.start(); } catch { on = false; cb.onListening(false); }
  };

  const start = async (opts?: { autoStop?: boolean }) => {
    if (on) return;
    aborted = false;
    const st = await voiceStatus(language);
    const Rec = (window as any).MediaRecorder as typeof MediaRecorder | undefined;
    if (!st || st.stt.engine === 'device' || !Rec || !navigator.mediaDevices?.getUserMedia) { startDevice(); return; }
    on = true;
    cb.onListening(true);  // the orb reacts at once; the permission prompt (first time only) comes after
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
    } catch {
      on = false; cb.onListening(false); cb.onError?.('mic_denied');
      return;
    }
    if (aborted || !on) { release(); return; }
    const mime = ['audio/mp4', 'audio/webm;codecs=opus', 'audio/webm'].find(m => Rec.isTypeSupported?.(m)) || '';
    const chunks: Blob[] = [];
    rec = mime ? new Rec(stream, { mimeType: mime }) : new Rec(stream);
    rec.ondataavailable = e => { if (e.data?.size) chunks.push(e.data); };
    rec.onstop = async () => {
      const type = (rec?.mimeType || mime || 'audio/mp4').split(';')[0];
      rec = null;
      release();
      if (aborted || Date.now() - startedAt < 350 || !chunks.length) { on = false; cb.onListening(false); return; }
      cb.onTranscribing?.(true);
      try {
        const res = await fetch(apiUrl(`/api/voice/transcribe?language=${encodeURIComponent(language)}`), { method: 'POST', headers: { 'Content-Type': type }, body: new Blob(chunks, { type }) });
        if (res.ok) {
          const d = await res.json();
          if (!aborted && d.text) cb.onText(d.text);
        } else {
          const d = await res.json().catch(() => ({}));
          if (d?.detail?.code === 'use_device') forgetVoiceStatus();
          cb.onError?.(d?.detail?.code || 'transcribe_failed');
        }
      } catch { cb.onError?.('network'); }
      cb.onTranscribing?.(false);
      on = false;
      cb.onListening(false);
    };
    const ac = audioContext();
    if (ac) {
      // auto stop (microphone button): after you have spoken, 1.4 s of silence ends the turn
      let heard = false;
      let quietSince = 0;
      stopMeter = meter(ac.createMediaStreamSource(stream), ac, level => {
        if (!opts?.autoStop || !rec) return;
        if (level > 0.09) { heard = true; quietSince = 0; return; }
        if (!heard) { if (Date.now() - startedAt > 12000) stop(); return; }
        quietSince = quietSince || Date.now();
        if (Date.now() - quietSince > 1400) stop();
      });
    }
    startedAt = Date.now();
    rec.start(250);
  };

  const stop = () => {
    if (dict) { try { dict.stop(); } catch { /* already stopped */ } return; }
    if (rec && rec.state !== 'inactive') { try { rec.stop(); } catch { /* already stopped */ } return; }
    if (on && !rec) { aborted = true; on = false; release(); cb.onListening(false); } // still waiting for the permission
  };
  const abort = () => {
    aborted = true;
    if (dict) { try { dict.abort(); } catch { /* gone */ } }
    stop();
  };
  return { start, stop, abort, active: () => on };
}

// -- speaking -------------------------------------------------------------------------------------------------------------
let playing: { audio: HTMLAudioElement | null; cancelled: boolean } | null = null;

/** Sentences grouped into pieces of ~220 characters: the first one plays while the next is being made. */
export function speechChunks(text: string): string[] {
  const parts = (text.match(/[^.!?…\n]+[.!?…]*\s*/g) || [text]).map(x => x.trim()).filter(Boolean);
  const out: string[] = [];
  for (const part of parts) {  // the first sentence alone (it starts sooner), then pieces of up to ~220 characters
    const last = out[out.length - 1];
    if (out.length > 1 && last.length + part.length < 220) out[out.length - 1] = `${last} ${part}`;
    else out.push(part);
  }
  return out;
}

async function fetchSpeech(text: string, language: string, voice?: string, engine?: string): Promise<Blob | null> {
  try {
    const res = await fetch(apiUrl('/api/voice/speak'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text, language, voice, engine }) });
    return res.ok ? await res.blob() : null;
  } catch { return null; }
}

function playBlob(blob: Blob, session: { audio: HTMLAudioElement | null; cancelled: boolean }): Promise<boolean> {
  return new Promise(resolve => {
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    session.audio = audio;
    let stopMeter: (() => void) | null = null;
    const done = (ok: boolean) => { stopMeter?.(); URL.revokeObjectURL(url); resolve(ok); };
    audio.onended = () => done(true);
    audio.onerror = () => done(false);
    const ac = audioContext();
    audio.play().then(() => {
      // route through the analyser only when the audio context is running, otherwise the sound would be muted
      if (ac && ac.state === 'running') {
        try { const src = ac.createMediaElementSource(audio); src.connect(ac.destination); stopMeter = meter(src, ac); } catch { /* plays anyway */ }
      }
    }).catch(() => done(false));
  });
}

export function stopSpeech() {
  if (playing) { playing.cancelled = true; try { playing.audio?.pause(); } catch { /* gone */ } playing = null; }
  emitLevel(0);
}

/** Speaks through the sidecar voice. Resolves false when nothing could be played (caller falls back). */
export async function speakText(text: string, language: string, opts?: { voice?: string; engine?: string }): Promise<boolean> {
  stopSpeech();
  const session = { audio: null as HTMLAudioElement | null, cancelled: false };
  playing = session;
  const chunks = speechChunks(text);
  if (!chunks.length) return false;
  let next = fetchSpeech(chunks[0], language, opts?.voice, opts?.engine);
  let playedAny = false;
  for (let i = 0; i < chunks.length; i++) {
    const blob = await next;
    if (session.cancelled) return true;
    if (!blob) return playedAny;
    if (i + 1 < chunks.length) next = fetchSpeech(chunks[i + 1], language, opts?.voice, opts?.engine);
    const ok = await playBlob(blob, session);
    if (session.cancelled) return true;
    if (!ok) return playedAny;
    playedAny = true;
  }
  if (playing === session) playing = null;
  return true;
}
