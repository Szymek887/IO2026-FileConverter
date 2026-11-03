import { delay, http, HttpResponse } from 'msw'
import { describe, expect, it, vi } from 'vitest'
import { config } from '../config'
import { fastHandlers, server, testFile } from '../test/setup'
import { ApiError, createJob, getFormats, getMe, requestOtp, SESSION_EXPIRED_EVENT, verifyOtp } from './client'

describe('API client', () => {
  it('maps the contract error body to ApiError', async () => {
    const error = await getMe().catch((e) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status: 401, code: 'UNAUTHENTICATED', message: 'Sesja wygasła. Zaloguj się ponownie.' })
  })

  it('falls back to a generic Polish message for a non-JSON error', async () => {
    server.use(http.get('*/api/formats', () => new HttpResponse('Bad gateway', { status: 502 })))
    await expect(getFormats()).rejects.toMatchObject({ status: 502, code: 'INTERNAL_ERROR', message: expect.stringMatching(/^Brak połączenia/) })
  })

  it('reports network failures as NETWORK_ERROR', async () => {
    server.use(http.get('*/api/formats', () => HttpResponse.error()))
    await expect(getFormats()).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
  })

  it('logs in with the OTP flow', async () => {
    const sent = await requestOtp('Jan@Example.com')
    expect(sent.resend_available_in).toBe(60)
    await expect(verifyOtp('jan@example.com', '000000')).rejects.toMatchObject({ code: 'INVALID_OTP' })
    const session = await verifyOtp('jan@example.com', '123456')
    expect(session.email).toBe('jan@example.com')
    await expect(getMe()).resolves.toMatchObject({ email: 'jan@example.com' })
  })

  it('exposes retry_after_seconds when a code is requested too early', async () => {
    await requestOtp('jan@example.com')
    const error = await requestOtp('jan@example.com').catch((e) => e)
    expect(error).toMatchObject({ status: 429, code: 'OTP_RATE_LIMITED' })
    expect(error.details.retry_after_seconds).toBeGreaterThan(0)
  })

  it('uploads with multipart/form-data and reports progress', async () => {
    server.resetHandlers(...fastHandlers('jan@example.com'))
    const progress: number[] = []
    const job = await createJob([testFile('glos.wav')], 'mp3', (p) => progress.push(p))
    expect(job).toMatchObject({ status: 'queued', target_format: 'mp3', result: null })
    expect(job.files[0]).toMatchObject({ name: 'glos.wav', extension: 'wav', category: 'audio' })
    expect(progress.at(-1)).toBe(1)
  })

  it('rejects an upload with the backend error (INVALID_TARGET)', async () => {
    server.resetHandlers(...fastHandlers('jan@example.com'))
    await expect(createJob([testFile('glos.wav')], 'png')).rejects.toMatchObject({
      status: 400,
      code: 'INVALID_TARGET',
      message: 'Nie można przekonwertować pliku „glos.wav” do formatu PNG.',
    })
  })

  it('gives up on a hung server with REQUEST_TIMEOUT', async () => {
    const previous = config.requestTimeoutMs
    config.requestTimeoutMs = 50
    try {
      server.use(http.get('*/api/formats', () => delay('infinite')))
      await expect(getFormats()).rejects.toMatchObject({ code: 'REQUEST_TIMEOUT' })
    } finally {
      config.requestTimeoutMs = previous
    }
  })

  it('signals session expiry only for UNAUTHENTICATED, not for a wrong OTP', async () => {
    const expired = vi.fn()
    window.addEventListener(SESSION_EXPIRED_EVENT, expired)
    try {
      await verifyOtp('jan@example.com', '000000').catch(() => {})
      expect(expired).not.toHaveBeenCalled()
      await getMe().catch(() => {})
      expect(expired).toHaveBeenCalledOnce()
    } finally {
      window.removeEventListener(SESSION_EXPIRED_EVENT, expired)
    }
  })
})
