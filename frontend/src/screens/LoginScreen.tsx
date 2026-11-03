import { useEffect, useRef, useState, type FormEvent } from 'react'
import { ApiError, requestOtp, verifyOtp } from '../api/client'
import type { SessionInfo } from '../api/types'
import { Mascot } from '../components/Mascot'
import { isValidEmail, maskEmail } from '../lib/format'

interface LoginScreenProps {
  onLoggedIn: (session: SessionInfo) => void
  /** Shown above the form, e.g. after the session expired. */
  notice?: string
}

/** Countdown in whole seconds; restart by calling `start(seconds)`. */
function useCountdown() {
  const [left, setLeft] = useState(0)
  useEffect(() => {
    if (left <= 0) return
    const timer = setTimeout(() => setLeft((s) => s - 1), 1000)
    return () => clearTimeout(timer)
  }, [left])
  return [left, setLeft] as const
}

export function LoginScreen({ onLoggedIn, notice }: LoginScreenProps) {
  const [step, setStep] = useState<'email' | 'code'>('email')
  const [email, setEmail] = useState('')
  const [code, setCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [info, setInfo] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [shake, setShake] = useState(0)
  const [resendIn, setResendIn] = useCountdown()
  const codeInput = useRef<HTMLInputElement>(null)
  const emailInput = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (step === 'code') codeInput.current?.focus()
    else emailInput.current?.focus()
  }, [step])

  const fail = (message: string) => {
    setError(message)
    setInfo(null)
    setShake((n) => n + 1)
  }

  const sendCode = async (): Promise<boolean> => {
    setBusy(true)
    try {
      const response = await requestOtp(email.trim())
      setResendIn(response.resend_available_in)
      setError(null)
      return true
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError(0, 'INTERNAL_ERROR', 'Wystąpił nieoczekiwany błąd.')
      if (err.code === 'OTP_RATE_LIMITED') {
        const retry = Number(err.details?.retry_after_seconds)
        if (retry > 0) setResendIn(retry)
        // A code was already sent recently – let the user enter it.
        if (step === 'email') {
          setInfo(err.message)
          return true
        }
      }
      fail(err.message)
      return false
    } finally {
      setBusy(false)
    }
  }

  const submitEmail = async (event: FormEvent) => {
    event.preventDefault()
    if (!isValidEmail(email)) {
      fail('Podaj poprawny adres e-mail.')
      return
    }
    setInfo(null)
    if (await sendCode()) {
      setCode('')
      setStep('code')
    }
  }

  const submitCode = async (event: FormEvent) => {
    event.preventDefault()
    const trimmed = code.replace(/\s/g, '')
    if (!/^\d{6}$/.test(trimmed)) {
      fail('Kod logowania składa się z 6 cyfr.')
      return
    }
    setBusy(true)
    try {
      const session = await verifyOtp(email.trim(), trimmed)
      onLoggedIn(session)
    } catch (e) {
      fail(e instanceof ApiError ? e.message : 'Wystąpił nieoczekiwany błąd.')
      setCode('')
      codeInput.current?.focus()
    } finally {
      setBusy(false)
    }
  }

  const resend = async () => {
    setInfo(null)
    if (await sendCode()) setInfo('Wysłaliśmy nowy kod.')
  }

  const changeEmail = () => {
    setStep('email')
    setError(null)
    setInfo(null)
    setCode('')
  }

  const isEmailStep = step === 'email'

  return (
    <section className="screen screen--login" aria-labelledby="login-title">
      <h1 id="login-title" className="screen__title">
        Zaloguj się, aby konwertować pliki
      </h1>

      <Mascot
        key={step}
        width={320}
        minHeight={400}
        face={error ? 'sad' : 'smile'}
        leftArm="down"
        rightArm={isEmailStep ? 'wave' : 'raised'}
        holding={isEmailStep ? undefined : 'envelope'}
        bubble={
          isEmailStep
            ? { text: notice ? 'Ojej, zaloguj się jeszcze raz 🙏' : 'Cześć! Podaj maila 👋', side: 'right' }
            : { text: 'Sprawdź skrzynkę! 📬', side: 'left' }
        }
        shakeKey={shake}
        className="screen__mascot"
      >
        {isEmailStep ? (
          <form className="form" onSubmit={submitEmail} noValidate>
            <p className="step-label">Krok 1 z 2</p>
            {notice && <p className="form__notice">{notice}</p>}
            <label className="visually-hidden" htmlFor="email">
              Adres e-mail
            </label>
            <input
              ref={emailInput}
              id="email"
              className="field"
              type="email"
              inputMode="email"
              autoComplete="email"
              placeholder="Email"
              value={email}
              onChange={(e) => {
                setEmail(e.target.value)
                setError(null)
              }}
              aria-invalid={error ? true : undefined}
              aria-describedby={error ? 'login-error' : undefined}
              disabled={busy}
            />
            {error && (
              <p id="login-error" className="form__error" role="alert">
                {error}
              </p>
            )}
            <button type="submit" className="btn btn--cta" disabled={busy}>
              {busy ? 'Wysyłam…' : 'Dalej →'}
            </button>
            <p className="form__hint">Wyślemy Ci hasło na maila</p>
          </form>
        ) : (
          <form className="form" onSubmit={submitCode} noValidate>
            <p className="step-label">Krok 2 z 2</p>
            <p className="form__lead">
              Hasło wysłaliśmy na <strong>{maskEmail(email.trim())}</strong>
            </p>
            <label className="visually-hidden" htmlFor="otp">
              Kod logowania z e-maila
            </label>
            <input
              ref={codeInput}
              id="otp"
              className="field field--code"
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              pattern="\d{6}"
              maxLength={6}
              placeholder="Hasło z maila"
              value={code}
              onChange={(e) => {
                setCode(e.target.value.replace(/\D/g, '').slice(0, 6))
                setError(null)
              }}
              aria-invalid={error ? true : undefined}
              aria-describedby={error ? 'login-error' : undefined}
              disabled={busy}
            />
            {error && (
              <p id="login-error" className="form__error" role="alert">
                {error}
              </p>
            )}
            {info && !error && <p className="form__info">{info}</p>}
            <button type="submit" className="btn btn--cta" disabled={busy}>
              {busy ? 'Sprawdzam…' : 'Zaloguj'}
            </button>
            <p className="form__hint">
              Nie dotarło?{' '}
              <button type="button" className="link-button link-button--strong" onClick={resend} disabled={busy || resendIn > 0}>
                {resendIn > 0 ? `Wyślij ponownie (${resendIn} s)` : 'Wyślij ponownie'}
              </button>
            </p>
            <button type="button" className="link-button link-button--pink" onClick={changeEmail} disabled={busy}>
              ← Zmień email
            </button>
          </form>
        )}
      </Mascot>
    </section>
  )
}
