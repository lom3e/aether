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
interface Session { stop: (() => void) | null; cancelled: boolean }
let playing: Session | null = null;

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

/** Plays through Web Audio (decoded buffer -> analyser -> speakers): WebKit can turn a media element routed into Web Audio
 * into silence, a decoded buffer always plays and still feeds the orb. A plain <audio> element is the fallback. */
async function playBlob(blob: Blob, session: Session): Promise<boolean> {
  const ac = audioContext();
  // without a click WebKit keeps resume() pending forever: wait a moment at most
  if (ac && ac.state === 'suspended') await Promise.race([ac.resume().catch(() => undefined), new Promise(r => setTimeout(r, 300))]);
  if (ac && ac.state === 'running') {  // a suspended context (no click yet) would stay silent: then the media element
    try {
      const buffer = await ac.decodeAudioData(await blob.arrayBuffer());
      if (session.cancelled) return true;
      return await new Promise<boolean>(resolve => {
        const src = ac.createBufferSource();
        src.buffer = buffer;
        src.connect(ac.destination);
        const stopMeter = meter(src, ac);
        let done = false;
        const finish = () => { if (done) return; done = true; stopMeter(); resolve(true); };
        src.onended = finish;
        session.stop = () => { try { src.stop(); } catch { /* ended */ } finish(); };
        src.start();
      });
    } catch { /* not decodable here: the media element below */ }
  }
  return new Promise(resolve => {
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    const done = (ok: boolean) => { URL.revokeObjectURL(url); resolve(ok); };
    session.stop = () => { try { audio.pause(); } catch { /* gone */ } done(true); };
    audio.onended = () => done(true);
    audio.onerror = () => done(false);
    audio.play().catch(() => done(false));
  });
}

export function stopSpeech() {
  if (playing) { playing.cancelled = true; playing.stop?.(); playing = null; }
  emitLevel(0);
}

// -- barge-in: talk over Aether and it stops to listen ---------------------------------------------------------------------
// While Aether speaks (and only then) the microphone level is watched, echo-cancelled so its own voice does not count; nothing is
// recorded. A third of a second of the user's voice stops the speech and hands the turn to whoever registered with onBargeIn.
const BARGE_KEY = 'aether_barge_in';
export function bargeInEnabled(): boolean { try { return localStorage.getItem(BARGE_KEY) !== '0'; } catch { return true; } }
export function setBargeIn(on: boolean) { try { localStorage.setItem(BARGE_KEY, on ? '1' : '0'); } catch { /* storage unavailable */ } }
let bargeHandler: (() => void) | null = null;
export function onBargeIn(fn: (() => void) | null) { bargeHandler = fn; }

async function watchForBargeIn(session: Session): Promise<() => void> {
  if (!bargeInEnabled() || !bargeHandler || !navigator.mediaDevices?.getUserMedia) return () => undefined;
  const ac = audioContext();
  if (!ac) return () => undefined;
  let stream: MediaStream | null = null;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: false } });
  } catch { return () => undefined; }
  if (session.cancelled) { stream.getTracks().forEach(t => t.stop()); return () => undefined; }
  const src = ac.createMediaStreamSource(stream);
  const an = ac.createAnalyser();
  an.fftSize = 512;
  src.connect(an);
  const buf = new Uint8Array(an.fftSize);
  const started = Date.now();
  let loudSince = 0;
  let raf = 0;
  let stopped = false;
  const stop = () => {
    if (stopped) return;
    stopped = true;
    cancelAnimationFrame(raf);
    try { src.disconnect(); } catch { /* gone */ }
    stream?.getTracks().forEach(t => t.stop());
  };
  const tick = () => {
    if (stopped || session.cancelled) { stop(); return; }
    an.getByteTimeDomainData(buf);
    let sum = 0;
    for (let i = 0; i < buf.length; i++) { const v = (buf[i] - 128) / 128; sum += v * v; }
    const level = Math.min(1, Math.sqrt(sum / buf.length) * 4.2);
    if (Date.now() - started > 700 && level > 0.16) {
      loudSince = loudSince || Date.now();
      if (Date.now() - loudSince > 320) {
        stop();
        stopSpeech();
        bargeHandler?.();
        return;
      }
    } else loudSince = 0;
    raf = requestAnimationFrame(tick);
  };
  raf = requestAnimationFrame(tick);
  return stop;
}

/** Speaks through the sidecar voice. Resolves false when nothing could be played (caller falls back). */
export async function speakText(text: string, language: string, opts?: { voice?: string; engine?: string }): Promise<boolean> {
  stopSpeech();
  const session: Session = { stop: null, cancelled: false };
  playing = session;
  const chunks = speechChunks(text);
  if (!chunks.length) return false;
  let next = fetchSpeech(chunks[0], language, opts?.voice, opts?.engine);
  let playedAny = false;
  let stopWatching: (() => void) | null = null;
  try {
    for (let i = 0; i < chunks.length; i++) {
      const blob = await next;
      if (session.cancelled) return true;
      if (!blob) return playedAny;
      if (i + 1 < chunks.length) next = fetchSpeech(chunks[i + 1], language, opts?.voice, opts?.engine);
      if (!stopWatching && !opts?.voice) stopWatching = await watchForBargeIn(session);  // not for a voice preview in Settings
      const ok = await playBlob(blob, session);
      if (session.cancelled) return true;
      if (!ok) return playedAny;
      playedAny = true;
    }
  } finally {
    stopWatching?.();
  }
  if (playing === session) playing = null;
  return true;
}
