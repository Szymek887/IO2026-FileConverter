import { useState } from 'react';
import type { FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { errorMessage } from '../api/client';
import { useAuth } from '../hooks/useAuth';
import { MascotCard } from '../components/MascotCard';
import { Icon } from '../components/Icon';
import { ErrorNotice } from '../components/Feedback';

export function LoginPage() {
  const { state, challenge, sendCode } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState(challenge?.email ?? '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = email.trim();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) { setError('Podaj poprawny adres e-mail.'); return; }
    setError('');
    setBusy(true);
    try { await sendCode(value); navigate('/verify'); }
    catch (error) { setError(errorMessage(error)); }
    finally { setBusy(false); }
  }

  return <main id="main-content" className="auth-main">
    <MascotCard speech="Hej! Wchodzisz?" className="auth-mascot">
      <span className="eyebrow">MAŁY KONWERTER, WIELE MOŻLIWOŚCI</span>
      <h1>Miło Cię widzieć!</h1>
      <p className="card-intro">Podaj e-mail. Wyślemy Ci kod, a potem<br className="desktop-break" /> zajmiemy się Twoimi plikami.</p>
      {state.notice && <p className="info-notice" role="status">{state.notice}</p>}
      <form onSubmit={event => void submit(event)} noValidate className="auth-form">
        <label htmlFor="email">Twój adres e-mail</label>
        <div className={`input-wrap ${error ? 'input-error' : ''}`}><Icon name="mail" /><input id="email" name="email" type="email" autoComplete="email" autoFocus required maxLength={254} placeholder="ty@przyklad.pl" value={email} disabled={busy} aria-invalid={!!error} aria-describedby={error ? 'login-error' : undefined} onChange={event => { setEmail(event.target.value); setError(''); }} /></div>
        <div id="login-error"><ErrorNotice messages={error ? [error] : []} /></div>
        <button className="button button-primary" type="submit" disabled={busy}>{busy ? 'Wysyłanie kodu…' : 'Wyślij kod logowania'}<Icon name="arrow" /></button>
      </form>
      <p className="card-footnote"><Icon name="shield" /> Bez hasła. Tylko jednorazowy kod.</p>
    </MascotCard>
    <p className="page-footnote">Audio, wideo i obrazy — po swojemu.</p>
  </main>;
}
