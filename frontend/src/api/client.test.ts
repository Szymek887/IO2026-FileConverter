import { describe, expect, it, vi } from 'vitest';
import { apiRequest, retryAfterSeconds, SESSION_EXPIRED_EVENT } from './client';

function response(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

describe('Klient API', () => {
  it('wysyła JSON i ciasteczko sesji', async () => {
    const fetchMock = vi.fn().mockResolvedValue(response({ status: 'ok' }));
    vi.stubGlobal('fetch', fetchMock);
    await apiRequest('/auth/request-otp', { method: 'POST', json: { email: 'test@example.com' } });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/auth/request-otp');
    expect(init.credentials).toBe('include');
    expect(init.body).toBe('{"email":"test@example.com"}');
    expect(init.headers.get('Content-Type')).toBe('application/json');
  });
  it('nie ustawia Content-Type dla multipart/form-data', async () => {
    const fetchMock = vi.fn().mockResolvedValue(response({ id: 'test' }, 202));
    vi.stubGlobal('fetch', fetchMock);
    const form = new FormData(); form.append('files', new File(['data'], 'a.wav'));
    await apiRequest('/jobs', { method: 'POST', body: form });
    expect(fetchMock.mock.calls[0][1].headers.has('Content-Type')).toBe(false);
    expect(fetchMock.mock.calls[0][1].body).toBe(form);
  });
  it('obsługuje pustą odpowiedź 204 po wylogowaniu', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })));
    await expect(apiRequest('/auth/logout', { method: 'POST' })).resolves.toBeUndefined();
  });
  it('błędny OTP 401 nie powoduje globalnego wylogowania', async () => {
    const expired = vi.fn(); window.addEventListener(SESSION_EXPIRED_EVENT, expired);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({ status: 'error', code: 'INVALID_OTP', message: 'Nieprawidłowy kod logowania.' }, 401)));
    await expect(apiRequest('/auth/verify-otp')).rejects.toMatchObject({ code: 'INVALID_OTP', httpStatus: 401 });
    expect(expired).not.toHaveBeenCalled();
    window.removeEventListener(SESSION_EXPIRED_EVENT, expired);
  });
  it('zgłasza wygaśnięcie sesji dla UNAUTHENTICATED', async () => {
    const expired = vi.fn(); window.addEventListener(SESSION_EXPIRED_EVENT, expired);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({ status: 'error', code: 'UNAUTHENTICATED', message: 'Sesja wygasła.' }, 401)));
    await expect(apiRequest('/formats')).rejects.toMatchObject({ code: 'UNAUTHENTICATED' });
    expect(expired).toHaveBeenCalledOnce();
    window.removeEventListener(SESSION_EXPIRED_EVENT, expired);
  });
  it('zachowuje polski komunikat i retry_after_seconds', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({ status: 'error', code: 'OTP_RATE_LIMITED', message: 'Poczekaj 42 s.', details: { retry_after_seconds: 42 } }, 429)));
    let caught: unknown;
    try { await apiRequest('/auth/request-otp'); } catch (error) { caught = error; }
    expect(caught).toMatchObject({ message: 'Poczekaj 42 s.' });
    expect(retryAfterSeconds(caught)).toBe(42);
  });
  it('rozróżnia brak połączenia i niepoprawną odpowiedź', async () => {
    const fetchMock = vi.fn().mockRejectedValueOnce(new TypeError('Failed to fetch')).mockResolvedValueOnce(new Response('<html>oops</html>'));
    vi.stubGlobal('fetch', fetchMock);
    await expect(apiRequest('/auth/me')).rejects.toMatchObject({ code: 'NETWORK_ERROR' });
    await expect(apiRequest('/auth/me')).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
  });
  it('przerywa żądanie po upływie timeoutu', async () => {
    vi.useFakeTimers();
    vi.stubGlobal('fetch', vi.fn((_url: string, init: RequestInit) => new Promise((_resolve, reject) => {
      init.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
    })));
    const assertion = expect(apiRequest('/auth/me', { timeoutMs: 20 })).rejects.toMatchObject({ code: 'REQUEST_TIMEOUT' });
    await vi.advanceTimersByTimeAsync(21);
    await assertion;
  });
});
