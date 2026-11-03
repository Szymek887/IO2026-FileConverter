import type { ReactNode } from 'react';
import { BrowserRouter, Link, Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider } from './auth/AuthProvider';
import { useAuth } from './hooks/useAuth';
import { AppHeader } from './components/AppHeader';
import { ErrorNotice, Loading } from './components/Feedback';
import { LoginPage } from './pages/LoginPage';
import { VerifyOtpPage } from './pages/VerifyOtpPage';
import { HomePage } from './pages/HomePage';

function RequireAuth({ children }: { children: ReactNode }) {
  const { state } = useAuth();
  return state.status === 'authenticated' ? children : <Navigate to="/login" replace />;
}

function GuestOnly({ children }: { children: ReactNode }) {
  const { state } = useAuth();
  return state.status === 'authenticated' ? <Navigate to="/" replace /> : children;
}

function AppContent() {
  const { state, retrySession } = useAuth();
  return <div className="app-shell">
    <a className="skip-link" href="#main-content">Przejdź do treści</a>
    <AppHeader />
    {state.status === 'checking' ? <main id="main-content" className="startup-main"><Loading label="Sprawdzanie sesji…" /></main>
      : state.status === 'error' ? <main id="main-content" className="startup-main"><div className="connection-card"><h1>Nie mogę się połączyć</h1><ErrorNotice messages={[state.notice]} /><button className="button button-primary" type="button" onClick={() => void retrySession()}>Spróbuj ponownie</button></div></main>
        : <Routes>
          <Route path="/" element={<RequireAuth><HomePage /></RequireAuth>} />
          <Route path="/login" element={<GuestOnly><LoginPage /></GuestOnly>} />
          <Route path="/verify" element={<GuestOnly><VerifyOtpPage /></GuestOnly>} />
          <Route path="*" element={<main id="main-content" className="startup-main"><div className="connection-card"><span className="eyebrow">404</span><h1>Tu nic nie ma.</h1><p>Wróćmy do plików.</p><Link className="button button-primary" to="/">Strona główna</Link></div></main>} />
        </Routes>}
  </div>;
}

export default function App() {
  return <BrowserRouter><AuthProvider><AppContent /></AuthProvider></BrowserRouter>;
}
