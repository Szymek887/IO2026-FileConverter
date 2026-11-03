import { useState } from 'react';
import { useAuth } from '../hooks/useAuth';
import { errorMessage } from '../api/client';
import { isDemo } from '../config';
import { Brand } from './Brand';
import { Icon } from './Icon';

export function AppHeader() {
  const { state, signOut } = useAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function logout() {
    setBusy(true);
    setError('');
    try { await signOut(); }
    catch (error) { setError(errorMessage(error)); }
    finally { setBusy(false); }
  }

  return <>
    {isDemo && <div className="demo-banner"><strong>Tryb demo</strong> · bez backendu i wysyłania e-maili · kod logowania: <strong>123456</strong></div>}
    <header className="app-header">
      <Brand />
      {state.status === 'authenticated' && <div className="account-menu">
        <span className="account-email" title={state.user.email}>{state.user.email}</span>
        <button className="logout-button" type="button" disabled={busy} onClick={() => void logout()}>
          <span>{busy ? 'Wylogowywanie…' : 'Wyloguj'}</span><span className="avatar"><Icon name="user" /></span>
        </button>
      </div>}
    </header>
    {error && <div className="header-error" role="alert">{error}<button type="button" className="text-button" onClick={() => setError('')}>Zamknij</button></div>}
  </>;
}
