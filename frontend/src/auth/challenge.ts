import { isDemo } from '../config';

export interface OtpChallenge {
  email: string;
  /** Lokalne terminy w milisekundach, wyliczane raz z odpowiedzi API. */
  expiresAt: number;
  resendAt: number;
}

const STORAGE_KEY = isDemo ? 'konwus:demo:pending-otp' : 'konwus:pending-otp';

export function readChallenge(): OtpChallenge | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const data = JSON.parse(raw) as OtpChallenge;
    if (typeof data.email === 'string' && Number.isFinite(data.expiresAt) && Number.isFinite(data.resendAt)) {
      // Pozwalamy otworzyć ekran wygasłego kodu, aby poprosić o nowy.
      return data;
    }
  } catch { /* Brak dostępu do storage nie blokuje logowania. */ }
  return null;
}

export function saveChallenge(challenge: OtpChallenge | null): void {
  try {
    if (challenge) sessionStorage.setItem(STORAGE_KEY, JSON.stringify(challenge));
    else sessionStorage.removeItem(STORAGE_KEY);
  } catch { /* W takim przypadku odświeżenie wróci do podania e-maila. */ }
}
