import { useCallback, useEffect, useRef, useState } from 'react';
import { canListen, createListener, type Listener } from '../voice/voiceIO';

/**
 * Push-to-dictate for the quick panel, through the same ears as the main window (voice/voiceIO): Whisper with the
 * user's key when there is one, else the Mac's dictation. "listening" is true only while the microphone (or the
 * dictation engine) is really on; without any engine the feature is reported as unsupported and the mic is hidden.
 */
export function useDictation(language: string, onText: (text: string) => void, onListening: (v: boolean) => void) {
  const recRef = useRef<Listener | null>(null);
  const [supported] = useState<boolean>(() => typeof window !== 'undefined' && canListen());
  const [error, setError] = useState<string | null>(null);
  const cb = useRef({ onText, onListening });
  cb.current = { onText, onListening };

  useEffect(() => {
    const rec = createListener(language, {
      onText: text => cb.current.onText(text),
      onListening: on => cb.current.onListening(on),
      onError: code => setError(code),
    });
    recRef.current = rec;
    return () => rec.abort();
  }, [language]);

  const stop = useCallback(() => { recRef.current?.stop(); }, []);
  const start = useCallback(() => {
    setError(null);
    void recRef.current?.start();
  }, []);

  return { supported, error, start, stop };
}
