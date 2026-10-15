import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * Push-to-dictate through the browser speech engine. "listening" becomes true only when the engine fires `onstart`,
 * and false again on `onend`/`onerror`; if the engine does not exist the feature is reported as unsupported and the
 * UI hides the microphone instead of pretending.
 */
export function useDictation(language: string, onText: (text: string) => void, onListening: (v: boolean) => void) {
  const recRef = useRef<any>(null);
  const [supported] = useState<boolean>(() => typeof window !== 'undefined' && !!((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition));
  const [error, setError] = useState<string | null>(null);
  const cb = useRef({ onText, onListening });
  cb.current = { onText, onListening };

  useEffect(() => () => recRef.current?.abort?.(), []);

  const stop = useCallback(() => {
    recRef.current?.stop?.();
  }, []);

  const start = useCallback(() => {
    const Ctor = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!Ctor) return;
    setError(null);
    const rec = new Ctor();
    rec.continuous = false;
    rec.interimResults = true;
    rec.lang = language === 'it' ? 'it-IT' : 'en-US';
    rec.onstart = () => cb.current.onListening(true);
    rec.onresult = (e: any) => {
      let text = '';
      for (let i = e.resultIndex; i < e.results.length; i++) text += e.results[i][0].transcript;
      if (text) cb.current.onText(text);
    };
    rec.onerror = (e: any) => {
      setError(e?.error || 'error');
      cb.current.onListening(false);
    };
    rec.onend = () => cb.current.onListening(false);
    recRef.current = rec;
    try {
      rec.start();
    } catch (e: any) {
      setError(String(e?.message || e));
      cb.current.onListening(false);
    }
  }, [language]);

  return { supported, error, start, stop };
}
