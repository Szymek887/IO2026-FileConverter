import type { AuthSession } from '../types/api';
import { demoFormats } from './formats';

interface DemoState {
  session: AuthSession | null;
  challenge: { email: string; expires: number; resend: number; attempts: number; used: boolean } | null;
}
const KEY = 'konwus:demo:server';
let memory: DemoState = { session: null, challenge: null };

function readState(): DemoState {
  try { return JSON.parse(sessionStorage.getItem(KEY) || 'null') || memory; }
  catch { return memory; }
}

function writeState(state: DemoState) {
  memory = state;
  try { sessionStorage.setItem(KEY, JSON.stringify(state)); } catch { /* fallback w pamięci */ }
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

function error(status: number, code: string, message: string, details: Record<string, unknown> | null = null): Response {
  return json({ status: 'error', code, message, details }, status);
}

async function pause(signal: AbortSignal | null | undefined) {
  if (signal?.aborted) throw new DOMException('Anulowano.', 'AbortError');
  await new Promise<void>((resolve, reject) => {
    const abort = () => { clearTimeout(timer); reject(new DOMException('Anulowano.', 'AbortError')); };
    const timer = setTimeout(() => { signal?.removeEventListener('abort', abort); resolve(); }, 180);
    signal?.addEventListener('abort', abort, { once: true });
  });
}

/** Jawny mock developerski. Nigdy nie wysyła e-maili i nie wykonuje konwersji. */
export async function mockFetch(url: string, init: RequestInit): Promise<Response> {
  await pause(init.signal);
  const path = new URL(url, window.location.origin).pathname;
  const method = init.method || 'GET';
  const state = readState();
  const now = Math.floor(Date.now() / 1000);
  const body = typeof init.body === 'string' ? JSON.parse(init.body) as { email?: string; code?: string } : {};
  if (state.session && state.session.session_expires <= now) { state.session = null; writeState(state); }

  if (path.endsWith('/auth/me') && method === 'GET') {
    return state.session ? json(state.session) : error(401, 'UNAUTHENTICATED', 'Sesja wygasła. Zaloguj się ponownie.');
  }
  if (path.endsWith('/auth/logout') && method === 'POST') {
    state.session = null; writeState(state);
    return new Response(null, { status: 204 });
  }
  if (path.endsWith('/auth/request-otp') && method === 'POST') {
    if (!body.email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(body.email)) return error(400, 'INVALID_EMAIL', 'Podaj poprawny adres e-mail.');
    if (state.challenge?.email === body.email && state.challenge.resend > now) {
      const seconds = state.challenge.resend - now;
      return error(429, 'OTP_RATE_LIMITED', `Nowy kod możesz wysłać za ${seconds} s.`, { retry_after_seconds: seconds });
    }
    state.challenge = { email: body.email, expires: now + 600, resend: now + 60, attempts: 0, used: false };
    writeState(state);
    return json({ status: 'ok', message: 'Tryb demo: użyj kodu 123456.', otp_expires: now + 600, resend_available_in: 60 }, 202);
  }
  if (path.endsWith('/auth/verify-otp') && method === 'POST') {
    if (!body.code || !/^\d{6}$/.test(body.code)) return error(400, 'VALIDATION_ERROR', 'Wpisz 6-cyfrowy kod.');
    if (!state.challenge || state.challenge.used || state.challenge.expires <= now || state.challenge.email !== body.email) {
      return error(401, 'OTP_EXPIRED', 'Kod logowania wygasł. Poproś o nowy kod.');
    }
    if (body.code !== '123456') {
      state.challenge.attempts += 1;
      if (state.challenge.attempts >= 5) {
        state.challenge.used = true; writeState(state);
        return error(429, 'TOO_MANY_ATTEMPTS', 'Przekroczono liczbę prób. Poproś o nowy kod.');
      }
      writeState(state);
      return error(401, 'INVALID_OTP', 'Nieprawidłowy kod logowania.');
    }
    state.challenge.used = true;
    state.session = { email: state.challenge.email, session_expires: now + 86400 };
    writeState(state);
    return json(state.session);
  }
  if (path.endsWith('/formats') && method === 'GET') {
    return state.session ? json(demoFormats) : error(401, 'UNAUTHENTICATED', 'Sesja wygasła. Zaloguj się ponownie.');
  }
  return error(404, 'NOT_FOUND', 'Ta funkcja nie jest częścią trybu demo osoby A.');
}
