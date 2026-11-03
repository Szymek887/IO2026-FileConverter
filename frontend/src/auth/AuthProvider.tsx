import { createContext, useCallback, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import * as auth from '../api/auth';
import { ApiError, errorMessage, isAbortError, SESSION_EXPIRED_EVENT } from '../api/client';
import type { AuthSession } from '../types/api';
import { readChallenge, saveChallenge } from './challenge';
import type { OtpChallenge } from './challenge';

type AuthState =
  | { status: 'checking'; user: null; notice: string }
  | { status: 'authenticated'; user: AuthSession; notice: string }
  | { status: 'anonymous'; user: null; notice: string }
  | { status: 'error'; user: null; notice: string };

interface AuthContextValue {
  state: AuthState;
  challenge: OtpChallenge | null;
  setChallenge: (challenge: OtpChallenge | null) => void;
  sendCode: (email: string) => Promise<void>;
  signIn: (email: string, code: string) => Promise<void>;
  signOut: () => Promise<void>;
  retrySession: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: 'checking', user: null, notice: '' });
  const [challenge, setPending] = useState<OtpChallenge | null>(readChallenge);

  const setChallenge = useCallback((next: OtpChallenge | null) => {
    saveChallenge(next);
    setPending(next);
  }, []);

  const checkSession = useCallback(async (signal?: AbortSignal) => {
    setState({ status: 'checking', user: null, notice: '' });
    try {
      const user = await auth.getSession(signal);
      if (!signal?.aborted) setState({ status: 'authenticated', user, notice: '' });
    } catch (error) {
      if (signal?.aborted || isAbortError(error)) return;
      if (error instanceof ApiError && error.code === 'UNAUTHENTICATED') {
        setState({ status: 'anonymous', user: null, notice: '' });
      } else {
        setState({ status: 'error', user: null, notice: errorMessage(error) });
      }
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void checkSession(controller.signal);
    return () => controller.abort();
  }, [checkSession]);

  useEffect(() => {
    const expire = () => setState(previous => previous.status === 'authenticated'
      ? { status: 'anonymous', user: null, notice: 'Sesja wygasła. Zaloguj się ponownie.' }
      : previous);
    window.addEventListener(SESSION_EXPIRED_EVENT, expire);
    if (state.status !== 'authenticated') return () => window.removeEventListener(SESSION_EXPIRED_EVENT, expire);
    const delay = Math.max(0, state.user.session_expires * 1000 - Date.now());
    const timer = window.setTimeout(expire, Math.min(delay, 2_147_483_647));
    return () => { clearTimeout(timer); window.removeEventListener(SESSION_EXPIRED_EVENT, expire); };
  }, [state]);

  async function sendCode(email: string) {
    const response = await auth.requestOtp(email);
    setChallenge({ email, expiresAt: response.otp_expires * 1000, resendAt: Date.now() + response.resend_available_in * 1000 });
  }

  async function signIn(email: string, code: string) {
    const user = await auth.verifyOtp(email, code);
    setChallenge(null);
    setState({ status: 'authenticated', user, notice: '' });
  }

  async function signOut() {
    await auth.logout();
    setChallenge(null);
    setState({ status: 'anonymous', user: null, notice: '' });
  }

  return <AuthContext.Provider value={{ state, challenge, setChallenge, sendCode, signIn, signOut, retrySession: checkSession }}>
    {children}
  </AuthContext.Provider>;
}
