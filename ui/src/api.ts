declare global {
  interface Window {
    __AETHER_API_URL__?: string;
    __AETHER_SESSION_TOKEN__?: string;
  }
}

export function getApiBase(): string {
  if (typeof window !== 'undefined' && window.__AETHER_API_URL__) {
    return window.__AETHER_API_URL__;
  }
  if (import.meta.env.VITE_API_URL) {
    return import.meta.env.VITE_API_URL;
  }
  if (typeof window !== 'undefined') {
    if (window.location.port === '5173') {
      return 'http://127.0.0.1:8000';
    }
    // If loaded via custom protocol (tauri://, app://) without injected API URL yet, fallback to 127.0.0.1:8000
    if (window.location.protocol === 'tauri:' || window.location.hostname === 'tauri.localhost') {
      return 'http://127.0.0.1:8000';
    }
    if (window.location.protocol.startsWith('http')) {
      return window.location.origin;
    }
  }
  return 'http://127.0.0.1:8000';
}

export function getSessionToken(): string | null {
  if (typeof window !== 'undefined' && window.__AETHER_SESSION_TOKEN__) {
    return window.__AETHER_SESSION_TOKEN__;
  }
  return null;
}

export const API_BASE = getApiBase();

export function apiUrl(path: string): string {
  return `${getApiBase()}${path}`;
}

// Transparently inject X-Aether-Session-Token into fetch calls if session token is configured
if (typeof window !== 'undefined' && typeof window.fetch === 'function') {
  const originalFetch = window.fetch.bind(window);
  window.fetch = async function (input: RequestInfo | URL, init?: RequestInit) {
    const token = getSessionToken();
    if (token) {
      init = init || {};
      const headers = new Headers(init.headers || {});
      if (!headers.has('X-Aether-Session-Token')) {
        headers.set('X-Aether-Session-Token', token);
      }
      init.headers = headers;
    }
    return originalFetch(input, init);
  };
}

export async function apiError(response: Response, fallback: string): Promise<Error> {
  const payload = await response.json().catch(() => ({}));
  let detail = fallback;
  if (typeof payload.detail === 'string') {
    detail = payload.detail;
  } else if (Array.isArray(payload.detail)) {
    const firstMessage = payload.detail[0]?.msg;
    if (firstMessage === 'JSON decode error') {
      detail = 'The request could not be understood. Check the fields and try again.';
    } else if (firstMessage === 'Field required') {
      detail = 'Complete the required fields before continuing.';
    } else if (firstMessage) {
      detail = 'Check the highlighted fields and try again.';
    }
  }
  return new Error(detail);
}
