/**
 * In-memory mock of the backend API, written against docs/api-contract.md.
 * Used by `npm run dev:mock`, by Vitest (msw/node) and by the Playwright E2E tests.
 *
 * Test hooks (file names):
 *   - contains "uszkodzony" -> upload rejected with 422 CORRUPTED_FILE
 *   - contains "blad"       -> job finishes with result.status = "error"
 * Login code is always MOCK_OTP_CODE (also printed to the console).
 */
import { http, HttpResponse, type HttpHandler } from 'msw'
import type { Format, FormatsResponse, Job, OutputFileInfo } from '../api/types'

export const MOCK_OTP_CODE = '123456'

export const MOCK_FORMATS: FormatsResponse = {
  max_file_size: 262_144_000,
  max_files_per_job: 2,
  categories: [
    { id: 'audio', label: 'Audio', formats: ['flac', 'mp3', 'wav'] },
    { id: 'video', label: 'Wideo', formats: ['gif', 'mp4', 'mov'] },
    { id: 'image', label: 'Obraz', formats: ['jpg', 'png', 'heic'] },
  ],
  conversions: {
    flac: ['mp3', 'wav'],
    mp3: ['flac', 'wav'],
    wav: ['flac', 'mp3'],
    gif: ['mp4', 'mov'],
    mp4: ['gif', 'mov'],
    mov: ['gif', 'mp4'],
    jpg: ['png', 'heic'],
    png: ['jpg', 'heic'],
    heic: ['jpg', 'png'],
  },
  extension_aliases: { jpeg: 'jpg', heif: 'heic' },
}

const MIME: Record<Format, string> = {
  mp3: 'audio/mpeg',
  flac: 'audio/flac',
  wav: 'audio/wav',
  gif: 'image/gif',
  mp4: 'video/mp4',
  mov: 'video/quicktime',
  jpg: 'image/jpeg',
  png: 'image/png',
  heic: 'image/heic',
}

export interface MockOptions {
  /** Time a job spends in `queued` (ms). */
  queuedMs?: number
  /** Time a job spends in `processing` (ms). */
  processingMs?: number
  /** Artificial latency of every response (ms). */
  latencyMs?: number
  /** Start already logged in as this e-mail. */
  loggedInAs?: string | null
  /** Persist the session in sessionStorage (browser dev mode survives reloads). */
  persistSession?: boolean
}

interface MockJob {
  job: Job
  createdMs: number
  owner: string
  fail: boolean
}

const SESSION_KEY = 'konwus-mock-session'
const now = () => Math.floor(Date.now() / 1000)
const uuid = () =>
  globalThis.crypto?.randomUUID?.() ??
  'xxxxxxxx-xxxx-4xxx-8xxx-xxxxxxxxxxxx'.replace(/x/g, () => Math.floor(Math.random() * 16).toString(16))

const error = (status: number, code: string, message: string, details: Record<string, unknown> | null = null) =>
  HttpResponse.json({ status: 'error', code, message, details }, { status })

const wait = (ms: number) => (ms > 0 ? new Promise((r) => setTimeout(r, ms)) : Promise.resolve())

function storageGet(): string | null {
  try {
    return sessionStorage.getItem(SESSION_KEY)
  } catch {
    return null
  }
}
function storageSet(value: string | null): void {
  try {
    if (value) sessionStorage.setItem(SESSION_KEY, value)
    else sessionStorage.removeItem(SESSION_KEY)
  } catch {
    /* storage unavailable – keep in memory only */
  }
}

export function createHandlers(options: MockOptions = {}): HttpHandler[] {
  const { queuedMs = 800, processingMs = 2500, latencyMs = 0, persistSession = false } = options

  let session: string | null = options.loggedInAs ?? (persistSession ? storageGet() : null)
  const otps = new Map<string, { attempts: number; sentAt: number }>()
  const jobs = new Map<string, MockJob>()

  const setSession = (email: string | null) => {
    session = email
    if (persistSession) storageSet(email)
  }

  /** Recomputes status/result from elapsed time (mimics the background worker). */
  function snapshot(entry: MockJob): Job {
    const elapsed = Date.now() - entry.createdMs
    const { job } = entry
    if (job.status === 'done' || job.status === 'error') return job
    if (elapsed < queuedMs) return job
    if (elapsed < queuedMs + processingMs) {
      job.status = 'processing'
      return job
    }
    const finished = now()
    if (entry.fail) {
      job.status = 'error'
      job.result = {
        finished_at: finished,
        status: 'error',
        message: `Nie udało się przekonwertować pliku „${job.files[0].name}”.`,
        output_files: [],
        expires_at: null,
      }
    } else {
      job.status = 'done'
      job.result = {
        finished_at: finished,
        status: 'success',
        message: 'Konwersja zakończona pomyślnie.',
        output_files: job.files.map<OutputFileInfo>((f, index) => ({
          index,
          name: `${f.name.replace(/\.[^.]+$/, '')}.${job.target_format}`,
          size: Math.max(1024, Math.round(f.size * 0.4)),
          url: `/api/jobs/${job.id}/files/${index}`,
        })),
        expires_at: finished + 24 * 60 * 60,
      }
    }
    return job
  }

  const requireSession = () => (session ? null : error(401, 'UNAUTHENTICATED', 'Sesja wygasła. Zaloguj się ponownie.'))

  const ownedJob = (id: string) => {
    const entry = jobs.get(id)
    if (!entry) return { response: error(404, 'NOT_FOUND', 'Nie znaleziono zadania.') }
    if (entry.owner !== session) return { response: error(403, 'FORBIDDEN', 'Brak dostępu do tego zadania.') }
    return { entry }
  }

  return [
    http.post('*/api/auth/request-otp', async ({ request }) => {
      await wait(latencyMs)
      const body = (await request.json().catch(() => null)) as { email?: unknown } | null
      const email = typeof body?.email === 'string' ? body.email.trim().toLowerCase() : ''
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
        return error(400, 'INVALID_EMAIL', 'Podaj poprawny adres e-mail.')
      }
      const previous = otps.get(email)
      if (previous) {
        const retry = 60 - (now() - previous.sentAt)
        if (retry > 0) {
          return error(429, 'OTP_RATE_LIMITED', `Nowy kod możesz wysłać za ${retry} s.`, {
            retry_after_seconds: retry,
          })
        }
      }
      otps.set(email, { attempts: 0, sentAt: now() })
      console.info(`[mock] Kod logowania dla ${email}: ${MOCK_OTP_CODE}`)
      return HttpResponse.json(
        {
          status: 'ok',
          message: `Wysłaliśmy kod logowania na adres ${email}.`,
          otp_expires: now() + 600,
          resend_available_in: 60,
        },
        { status: 202 },
      )
    }),

    http.post('*/api/auth/verify-otp', async ({ request }) => {
      await wait(latencyMs)
      const body = (await request.json().catch(() => null)) as { email?: unknown; code?: unknown } | null
      const email = typeof body?.email === 'string' ? body.email.trim().toLowerCase() : ''
      const code = typeof body?.code === 'string' ? body.code : ''
      if (!/^\d{6}$/.test(code)) return error(400, 'VALIDATION_ERROR', 'Nieprawidłowe dane żądania.')
      const otp = otps.get(email)
      if (!otp) return error(401, 'OTP_EXPIRED', 'Kod logowania wygasł. Poproś o nowy kod.')
      if (code !== MOCK_OTP_CODE) {
        otp.attempts++
        if (otp.attempts >= 5) {
          otps.delete(email)
          return error(429, 'TOO_MANY_ATTEMPTS', 'Przekroczono liczbę prób. Poproś o nowy kod.')
        }
        return error(401, 'INVALID_OTP', 'Nieprawidłowy kod logowania.')
      }
      otps.delete(email)
      setSession(email)
      return HttpResponse.json({ email, session_expires: now() + 86_400 })
    }),

    http.get('*/api/auth/me', async () => {
      await wait(latencyMs)
      return requireSession() ?? HttpResponse.json({ email: session, session_expires: now() + 86_400 })
    }),

    http.post('*/api/auth/logout', async () => {
      await wait(latencyMs)
      setSession(null)
      return new HttpResponse(null, { status: 204 })
    }),

    http.get('*/api/formats', async () => {
      await wait(latencyMs)
      return requireSession() ?? HttpResponse.json(MOCK_FORMATS)
    }),

    http.post('*/api/jobs', async ({ request }) => {
      await wait(latencyMs)
      const unauthenticated = requireSession()
      if (unauthenticated) return unauthenticated

      const form = await request.formData()
      const files = form.getAll('files').filter((f): f is File => typeof f !== 'string')
      const target = form.get('target_format')
      if (files.length === 0) return error(400, 'NO_FILES', 'Nie wybrano żadnego pliku.')
      if (files.length > 2) return error(400, 'TOO_MANY_FILES', 'Możesz przesłać maksymalnie 2 pliki naraz.')
      if (typeof target !== 'string' || !target) {
        return error(400, 'VALIDATION_ERROR', 'Nieprawidłowe dane żądania.', { fields: ['target_format'] })
      }

      const inputs: Job['files'] = []
      for (const file of files) {
        const raw = file.name.split('.').pop()?.toLowerCase() ?? ''
        const ext = (MOCK_FORMATS.extension_aliases[raw] ?? raw) as Format
        if (!(ext in MOCK_FORMATS.conversions)) {
          return error(415, 'UNSUPPORTED_FORMAT', `Format pliku „${file.name}” nie jest obsługiwany.`, { file: file.name })
        }
        if (file.size > MOCK_FORMATS.max_file_size) {
          return error(413, 'FILE_TOO_LARGE', `Plik „${file.name}” przekracza maksymalny rozmiar 250 MB.`, {
            file: file.name,
          })
        }
        if (!MOCK_FORMATS.conversions[ext].includes(target as Format)) {
          return error(400, 'INVALID_TARGET', `Nie można przekonwertować pliku „${file.name}” do formatu ${target.toUpperCase()}.`, {
            file: file.name,
          })
        }
        if (file.name.toLowerCase().includes('uszkodzony')) {
          return error(422, 'CORRUPTED_FILE', `Plik „${file.name}” jest uszkodzony lub ma nieprawidłową zawartość.`, {
            file: file.name,
          })
        }
        const category = MOCK_FORMATS.categories.find((c) => c.formats.includes(ext))!.id
        inputs.push({ id: uuid(), name: file.name, extension: ext, category, size: file.size })
      }

      const job: Job = {
        id: uuid(),
        created_at: now(),
        target_format: target as Format,
        status: 'queued',
        files: inputs,
        result: null,
      }
      jobs.set(job.id, {
        job,
        createdMs: Date.now(),
        owner: session!,
        fail: files.some((f) => f.name.toLowerCase().includes('blad')),
      })
      return HttpResponse.json(structuredClone(job), { status: 202 })
    }),

    http.get('*/api/jobs', async () => {
      await wait(latencyMs)
      const unauthenticated = requireSession()
      if (unauthenticated) return unauthenticated
      const items = [...jobs.values()]
        .filter((e) => e.owner === session)
        .sort((a, b) => b.createdMs - a.createdMs)
        .map((e) => structuredClone(snapshot(e)))
      return HttpResponse.json({ items })
    }),

    http.get('*/api/jobs/:jobId', async ({ params }) => {
      await wait(latencyMs)
      const unauthenticated = requireSession()
      if (unauthenticated) return unauthenticated
      const { entry, response } = ownedJob(String(params.jobId))
      if (response) return response
      return HttpResponse.json(structuredClone(snapshot(entry)))
    }),

    http.get('*/api/jobs/:jobId/files/:index', async ({ params }) => {
      await wait(latencyMs)
      const unauthenticated = requireSession()
      if (unauthenticated) return unauthenticated
      const { entry, response } = ownedJob(String(params.jobId))
      if (response) return response
      const job = snapshot(entry)
      const output = job.status === 'done' ? job.result?.output_files[Number(params.index)] : undefined
      if (!output) return error(404, 'NOT_FOUND', 'Nie znaleziono pliku.')
      const content = new TextEncoder().encode(`KONWUS MOCK ${output.name}\n`)
      return new HttpResponse(content, {
        status: 200,
        headers: {
          'Content-Type': MIME[job.target_format],
          'Content-Disposition': `attachment; filename*=UTF-8''${encodeURIComponent(output.name)}`,
        },
      })
    }),
  ]
}
