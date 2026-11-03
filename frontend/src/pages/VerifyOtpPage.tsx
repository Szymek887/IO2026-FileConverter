import { useState } from 'react';
import type { FormEvent } from 'react';
import { Link, Navigate } from 'react-router-dom';
import { ApiError, errorMessage, retryAfterSeconds } from '../api/client';
import { useAuth } from '../hooks/useAuth';
import { formatCountdown, useCountdown } from '../hooks/useCountdown';
import { MascotCard } from '../components/MascotCard';
import { Icon } from '../components/Icon';
import { ErrorNotice } from '../components/Feedback';

export function VerifyOtpPage() {
  const { challenge, setChallenge, signIn, sendCode } = useAuth();
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState<'verify' | 'resend' | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [requiresNewCode, setRequiresNewCode] = useState(false);
  const validFor = useCountdown(challenge?.expiresAt ?? 0);
  const resendIn = useCountdown(challenge?.resendAt ?? 0);
  if (!challenge) return <Navigate to="/login" replace />;
  const pending = challenge;

  async function verify(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!/^\d{6}$/.test(code)) { setError('Wpisz 6-cyfrowy kod z wiadomości e-mail.'); return; }
    if (validFor === 0 || requiresNewCode) return;
    setError(''); setNotice(''); setBusy('verify');
    try { await signIn(pending.email, code); }
    catch (error) {
      setError(errorMessage(error));
      if (error instanceof ApiError && ['OTP_EXPIRED', 'TOO_MANY_ATTEMPTS'].includes(error.code)) setRequiresNewCode(true);
    } finally { setBusy(null); }
  }

  async function resend() {
    if (resendIn > 0) return;
    setError(''); setNotice(''); setBusy('resend');
    try {
      await sendCode(pending.email);
      setCode(''); setRequiresNewCode(false); setNotice('Wysłaliśmy nowy kod. Sprawdź pocztę.');
    } catch (error) {
      setError(errorMessage(error));
      const seconds = retryAfterSeconds(error);
      if (seconds !== null) setChallenge({ ...pending, resendAt: Date.now() + seconds * 1000 });
    } finally { setBusy(null); }
  }

  return <main id="main-content" className="auth-main">
    <MascotCard speech="Zerknij do skrzynki!" className="auth-mascot">
      <span className="eyebrow">JESZCZE JEDEN MAŁY KROK</span>
      <h1>Masz wiadomość!</h1>
      <p className="card-intro">Kod logowania wysłaliśmy na<br /><strong className="otp-email">{pending.email}</strong></p>
      <form className="auth-form" onSubmit={event => void verify(event)} noValidate>
        <label htmlFor="otp-code">6-cyfrowy kod</label>
        <input className={`otp-input ${error ? 'input-error' : ''}`} id="otp-code" name="code" type="text" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} autoFocus placeholder="000000" required value={code} disabled={busy !== null || validFor === 0 || requiresNewCode} aria-invalid={!!error} aria-describedby="otp-hint otp-error"
          onChange={event => { setCode(event.target.value.replace(/\D/g, '').slice(0, 6)); setError(''); }} />
        <p id="otp-hint" className="code-timer">{validFor > 0 ? <>Kod ważny jeszcze <strong>{formatCountdown(validFor)}</strong></> : 'Kod wygasł. Poproś o nowy poniżej.'}</p>
        <div id="otp-error"><ErrorNotice messages={error ? [error] : []} /></div>
        {notice && <p className="info-notice" role="status">{notice}</p>}
        <button className="button button-primary" type="submit" disabled={busy !== null || validFor === 0 || requiresNewCode}>{busy === 'verify' ? 'Sprawdzanie kodu…' : 'Zaloguj się'}<Icon name="arrow" /></button>
      </form>
      <div className="resend-section"><span>Nie dotarł? Sprawdź też spam.</span><button className="text-button" type="button" disabled={busy !== null || resendIn > 0} onClick={() => void resend()}>{busy === 'resend' ? 'Wysyłanie…' : resendIn > 0 ? `Wyślij ponownie za ${resendIn} s` : 'Wyślij kod ponownie'}</button></div>
      <Link className={`back-link ${busy ? 'link-disabled' : ''}`} to="/login" onClick={event => { if (busy) event.preventDefault(); else setChallenge(null); }}>Zmień adres e-mail</Link>
    </MascotCard>
    <p className="page-footnote">Kod jest jednorazowy. Nie musisz go zapamiętywać.</p>
  </main>;
}
