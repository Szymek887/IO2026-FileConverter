import { ApiError, apiRequest } from './client';
import type { AuthSession, OtpResponse } from '../types/api';

function parseSession(data: AuthSession): AuthSession {
  if (!data || typeof data.email !== 'string' || !Number.isFinite(data.session_expires)) {
    throw new ApiError(200, 'INVALID_RESPONSE', 'Nie udało się odczytać sesji. Spróbuj ponownie.');
  }
  if (data.session_expires * 1000 <= Date.now()) {
    throw new ApiError(401, 'UNAUTHENTICATED', 'Sesja wygasła. Zaloguj się ponownie.');
  }
  return data;
}

export async function requestOtp(email: string, signal?: AbortSignal): Promise<OtpResponse> {
  const data = await apiRequest<OtpResponse>('/auth/request-otp', { method: 'POST', json: { email }, signal });
  if (!data || data.status !== 'ok' || !Number.isFinite(data.otp_expires) || !Number.isFinite(data.resend_available_in)) {
    throw new ApiError(202, 'INVALID_RESPONSE', 'Nie udało się odczytać informacji o kodzie. Spróbuj ponownie.');
  }
  return data;
}

export async function verifyOtp(email: string, code: string): Promise<AuthSession> {
  return parseSession(await apiRequest<AuthSession>('/auth/verify-otp', { method: 'POST', json: { email, code } }));
}

export async function getSession(signal?: AbortSignal): Promise<AuthSession> {
  return parseSession(await apiRequest<AuthSession>('/auth/me', { signal }));
}

export function logout(): Promise<void> {
  return apiRequest<void>('/auth/logout', { method: 'POST' });
}
