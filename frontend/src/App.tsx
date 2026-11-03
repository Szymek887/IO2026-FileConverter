import { useCallback, useEffect, useState } from 'react'
import { ApiError, getMe, logout } from './api/client'
import type { SessionInfo } from './api/types'
import { Header } from './components/Header'
import { ConverterScreen } from './screens/ConverterScreen'
import { LoginScreen } from './screens/LoginScreen'

type AuthState = { status: 'checking' } | { status: 'anonymous'; notice?: string } | { status: 'in'; session: SessionInfo }

export default function App() {
  const [auth, setAuth] = useState<AuthState>({ status: 'checking' })

  // Auto-login on page load (contract §3: GET /auth/me).
  useEffect(() => {
    let active = true
    getMe()
      .then((session) => active && setAuth({ status: 'in', session }))
      .catch((e) => {
        if (!active) return
        const notice = e instanceof ApiError && e.code !== 'UNAUTHENTICATED' ? e.message : undefined
        setAuth({ status: 'anonymous', notice })
      })
    return () => {
      active = false
    }
  }, [])

  const onUnauthenticated = useCallback((message: string) => setAuth({ status: 'anonymous', notice: message }), [])

  const onLogout = async () => {
    try {
      await logout()
    } catch {
      /* logout is idempotent – go to the login screen anyway */
    }
    setAuth({ status: 'anonymous' })
  }

  return (
    <div className="app">
      <Header email={auth.status === 'in' ? auth.session.email : undefined} onLogout={onLogout} />
      <main className="main">
        {auth.status === 'checking' && (
          <div className="loader" role="status" aria-label="Ładowanie">
            <span className="loader__dot" />
            <span className="loader__dot" />
            <span className="loader__dot" />
          </div>
        )}
        {auth.status === 'anonymous' && (
          <LoginScreen notice={auth.notice} onLoggedIn={(session) => setAuth({ status: 'in', session })} />
        )}
        {auth.status === 'in' && <ConverterScreen key={auth.session.email} onUnauthenticated={onUnauthenticated} />}
      </main>
    </div>
  )
}
