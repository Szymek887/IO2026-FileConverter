import { Component, StrictMode } from 'react';
import type { ErrorInfo, ReactNode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import './styles.css';

class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(error: Error, info: ErrorInfo) {
    if (import.meta.env.DEV) console.error(error, info);
  }
  render() {
    if (this.state.failed) return <main className="startup-main"><div className="connection-card"><h1>Coś poszło nie tak.</h1><p>Odśwież stronę i spróbuj ponownie.</p><button type="button" className="button button-primary" onClick={() => window.location.reload()}>Odśwież stronę</button></div></main>;
    return this.props.children;
  }
}

createRoot(document.getElementById('root')!).render(<StrictMode><ErrorBoundary><App /></ErrorBoundary></StrictMode>);
