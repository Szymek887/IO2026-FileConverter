import { useCallback, useEffect, useState } from 'react'
import { ApiError, getMe, logout, SESSION_EXPIRED_EVENT } from './api/client'
import type { SessionInfo } from './api/types'
import { Header } from './components/Header'
import { Mascot } from './components/Mascot'
import { ConverterScreen } from './screens/ConverterScreen'
import { LoginScreen } from './screens/LoginScreen'

type AuthState =
  | { status: 'checking' }
  | { status: 'offline'; message: string }
  | { status: 'anonymous'; notice?: string }
  | { status: 'in'; session: SessionInfo }

const SESSION_EXPIRED = 'Sesja wygasła. Zaloguj się ponownie.'
/** setTimeout fires immediately for delays above this (≈ 24.8 days). */
const MAX_TIMEOUT_MS = 2_147_483_647
const isMock = import.meta.env.VITE_API_MOCK === 'true'

/**
 * Asks the backend who is logged in. Anything other than `401 UNAUTHENTICATED` means the backend
 * is unreachable or broken – the app shows that instead of a login form that cannot work.
 */
async function resolveSession(): Promise<AuthState> {
  try {
    return { status: 'in', session: await getMe() }
  } catch (e) {
    if (e instanceof ApiError && e.code === 'UNAUTHENTICATED') return { status: 'anonymous' }
    return { status: 'offline', message: e instanceof ApiError ? e.message : 'Wystąpił błąd.' }
  }
}

export default function App() {
  const [auth, setAuth] = useState<AuthState>({ status: 'checking' })

  // Auto-login on page load (contract §3: GET /auth/me).
  useEffect(() => {
    let active = true
    void resolveSession().then((next) => active && setAuth(next))
    return () => {
      active = false
    }
  }, [])

  const onUnauthenticated = useCallback(
    (message: string) =>
      setAuth((prev) => (prev.status === 'in' ? { status: 'anonymous', notice: message || SESSION_EXPIRED } : prev)),
    [],
  )

  // Leave the converter when any request reports `UNAUTHENTICATED`, or when the session runs out.
  const sessionExpires = auth.status === 'in' ? auth.session.session_expires : null
  useEffect(() => {
    if (sessionExpires === null) return
    const onExpired = (event: Event) => onUnauthenticated((event as CustomEvent<string>).detail)
    window.addEventListener(SESSION_EXPIRED_EVENT, onExpired)
    const delay = Math.min(Math.max(0, sessionExpires * 1000 - Date.now()), MAX_TIMEOUT_MS)
    const timer = setTimeout(() => onUnauthenticated(SESSION_EXPIRED), delay)
    return () => {
      window.removeEventListener(SESSION_EXPIRED_EVENT, onExpired)
      clearTimeout(timer)
    }
  }, [sessionExpires, onUnauthenticated])

  const onLogout = async () => {
    try {
      await logout()
    } catch {
      /* logout is idempotent – go to the login screen anyway */
    }
    setAuth({ status: 'anonymous' })
  }

  const retry = () => {
    setAuth({ status: 'checking' })
    void resolveSession().then(setAuth)
  }

  return (
    <div className="app">
      <a className="skip-link" href="#main">
        Przejdź do treści
      </a>
      {isMock && (
        <p className="mock-banner">
          <strong>Tryb mock</strong> · bez backendu · kod logowania: <strong>123456</strong>
        </p>
      )}
      <Header email={auth.status === 'in' ? auth.session.email : undefined} onLogout={onLogout} />
      <main className="main" id="main" tabIndex={-1}>
        {auth.status === 'checking' && (
          <div className="loader" role="status" aria-label="Ładowanie">
            <span className="loader__dot" />
            <span className="loader__dot" />
            <span className="loader__dot" />
          </div>
        )}
        {auth.status === 'offline' && (
          <section className="screen screen--home" aria-label="Brak połączenia">
            <Mascot
              width={340}
              minHeight={380}
              face="sad"
              leftArm="down"
              rightArm="down"
              bubble={{ text: 'Nie mogę się połączyć… 😵', side: 'right' }}
              className="screen__mascot"
            >
              <div className="home">
                <p className="form__error" role="alert">
                  {auth.message}
                </p>
                <button type="button" className="btn btn--cta" onClick={retry}>
                  Spróbuj ponownie
                </button>
              </div>
            </Mascot>
          </section>
        )}
        {auth.status === 'anonymous' && (
          <LoginScreen notice={auth.notice} onLoggedIn={(session) => setAuth({ status: 'in', session })} />
        )}
        {auth.status === 'in' && <ConverterScreen key={auth.session.email} onUnauthenticated={onUnauthenticated} />}
      </main>
    </div>
  )
}
