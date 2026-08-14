export const API_BASE = import.meta.env.VITE_API_URL
  || (window.location.port === '5173' ? 'http://localhost:8000' : window.location.origin);

export function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
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
