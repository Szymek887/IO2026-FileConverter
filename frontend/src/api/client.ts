import { apiBaseUrl } from '../config';
import type { ApiErrorBody } from '../types/api';

export const SESSION_EXPIRED_EVENT = 'konwus:session-expired';

export class ApiError extends Error {
  readonly httpStatus: number;
  readonly code: string;
  readonly details: Record<string, unknown> | null;

  constructor(httpStatus: number, code: string, message: string, details: Record<string, unknown> | null = null) {
    super(message);
    this.name = 'ApiError';
    this.httpStatus = httpStatus;
    this.code = code;
    this.details = details;
  }
}

interface ApiOptions extends Omit<RequestInit, 'body'> {
  json?: unknown;
  body?: BodyInit;
  timeoutMs?: number;
}

/** Wspólny klient również dla osoby B. Dla FormData nie ustawiamy Content-Type. */
export async function apiRequest<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const { json, body, timeoutMs = 20_000, signal, ...requestOptions } = options;
  const headers = new Headers(options.headers);
  headers.set('Accept', 'application/json');
  if (json !== undefined) headers.set('Content-Type', 'application/json');

  const controller = new AbortController();
  const abort = () => controller.abort();
  if (signal?.aborted) controller.abort();
  signal?.addEventListener('abort', abort, { once: true });
  let timedOut = false;
  const timer = timeoutMs > 0 ? setTimeout(() => { timedOut = true; controller.abort(); }, timeoutMs) : undefined;

  try {
    const init: RequestInit = {
      ...requestOptions,
      headers,
      body: json !== undefined ? JSON.stringify(json) : body,
      credentials: 'include',
      signal: controller.signal,
    };
    const url = `${apiBaseUrl}${path}`;
    // Warunek jest stały podczas budowania; produkcyjny bundle nie zawiera mocka.
    const response = import.meta.env.DEV && import.meta.env.MODE === 'demo'
      ? await (await import('../demo/mockApi')).mockFetch(url, init)
      : await fetch(url, init);

    if (response.status === 204) return undefined as T;

    let payload: unknown;
    try {
      payload = await response.json();
    } catch {
      throw new ApiError(response.status, 'INVALID_RESPONSE', 'Serwer zwrócił nieprawidłową odpowiedź. Spróbuj ponownie.');
    }

    if (!response.ok) {
      const data = payload as Partial<ApiErrorBody> | null;
      const code = typeof data?.code === 'string' ? data.code : 'UNKNOWN_ERROR';
      const message = typeof data?.message === 'string' ? data.message : 'Nie udało się wykonać operacji. Spróbuj ponownie.';
      if (response.status === 401 && code === 'UNAUTHENTICATED') {
        window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
      }
      const details = data?.details && typeof data.details === 'object' ? data.details : null;
      throw new ApiError(response.status, code, message, details);
    }

    return payload as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (timedOut) throw new ApiError(408, 'REQUEST_TIMEOUT', 'Serwer nie odpowiedział na czas. Spróbuj ponownie.');
    if (controller.signal.aborted) throw new DOMException('Żądanie anulowane.', 'AbortError');
    throw new ApiError(0, 'NETWORK_ERROR', 'Nie można połączyć się z serwerem. Sprawdź połączenie i spróbuj ponownie.');
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener('abort', abort);
  }
}

export function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : 'Wystąpił błąd. Spróbuj ponownie.';
}

export function retryAfterSeconds(error: unknown): number | null {
  if (!(error instanceof ApiError)) return null;
  const value = error.details?.retry_after_seconds;
  return typeof value === 'number' && Number.isFinite(value) ? Math.max(0, Math.ceil(value)) : null;
}

export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError';
}
