import type {
  ApiErrorBody,
  Format,
  FormatsResponse,
  Job,
  RequestOtpResponse,
  SessionInfo,
} from './types'
import { config } from '../config'

/** Base path of the API. Same origin in production, proxied by Vite in development. */
export const API_BASE = '/api'

const GENERIC_ERROR = 'Wystąpił nieoczekiwany błąd serwera.'
const NETWORK_ERROR = 'Brak połączenia z serwerem. Sprawdź internet i spróbuj ponownie.'
const TIMEOUT_ERROR = 'Serwer nie odpowiedział na czas. Spróbuj ponownie.'

/**
 * Dispatched on `window` whenever any API call returns `401 UNAUTHENTICATED`, so the app can go
 * back to the login screen from anywhere. Other 401 codes (`INVALID_OTP`, `OTP_EXPIRED`) do not
 * end the session and do not trigger it.
 */
export const SESSION_EXPIRED_EVENT = 'konwus:session-expired'

/** A non-2xx API response (or a network failure, `code = "NETWORK_ERROR"`). */
export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details: Record<string, unknown> | null

  constructor(status: number, code: string, message: string, details?: Record<string, unknown> | null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details ?? null
  }
}

function isErrorBody(value: unknown): value is ApiErrorBody {
  return (
    typeof value === 'object' &&
    value !== null &&
    (value as ApiErrorBody).status === 'error' &&
    typeof (value as ApiErrorBody).code === 'string'
  )
}

function errorFromBody(status: number, body: unknown): ApiError {
  if (!isErrorBody(body)) return new ApiError(status, 'INTERNAL_ERROR', GENERIC_ERROR)
  if (status === 401 && body.code === 'UNAUTHENTICATED') {
    window.dispatchEvent(new CustomEvent(SESSION_EXPIRED_EVENT, { detail: body.message }))
  }
  return new ApiError(status, body.code, body.message, body.details)
}

async function parseJson(response: Response): Promise<unknown> {
  const text = await response.text()
  if (!text) return null
  try {
    return JSON.parse(text)
  } catch {
    return null
  }
}

/**
 * JSON request with a timeout (`config.requestTimeoutMs`), so a hung backend shows an error
 * instead of an endless spinner. Uploads and downloads have their own functions without it,
 * because large files legitimately take long.
 */
async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), config.requestTimeoutMs)
  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, {
      credentials: 'include',
      ...init,
      headers: { Accept: 'application/json', ...init.headers },
      signal: controller.signal,
    })
  } catch {
    if (controller.signal.aborted) throw new ApiError(0, 'REQUEST_TIMEOUT', TIMEOUT_ERROR)
    throw new ApiError(0, 'NETWORK_ERROR', NETWORK_ERROR)
  } finally {
    clearTimeout(timer) // the timeout covers waiting for the server, not reading the small JSON body
  }
  const body = await parseJson(response)
  if (!response.ok) throw errorFromBody(response.status, body)
  return body as T
}

function postJson<T>(path: string, data: unknown): Promise<T> {
  return request<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

// --- Auth ---

export const requestOtp = (email: string) => postJson<RequestOtpResponse>('/auth/request-otp', { email })

export const verifyOtp = (email: string, code: string) =>
  postJson<SessionInfo>('/auth/verify-otp', { email, code })

export const getMe = () => request<SessionInfo>('/auth/me')

export const logout = () => request<null>('/auth/logout', { method: 'POST' })

// --- Formats & jobs ---

export const getFormats = () => request<FormatsResponse>('/formats')

export const getJob = (jobId: string) => request<Job>(`/jobs/${encodeURIComponent(jobId)}`)

/**
 * Upload files and start a conversion (`POST /api/jobs`).
 * Uses XMLHttpRequest because `fetch` cannot report upload progress (see contract §5).
 */
export function createJob(
  files: File[],
  targetFormat: Format,
  onProgress?: (fraction: number) => void,
): Promise<Job> {
  const form = new FormData()
  for (const file of files) form.append('files', file)
  form.append('target_format', targetFormat)

  return new Promise<Job>((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${API_BASE}/jobs`)
    xhr.withCredentials = true
    xhr.setRequestHeader('Accept', 'application/json')
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && event.total > 0) onProgress?.(event.loaded / event.total)
    }
    xhr.onload = () => {
      let body: unknown = null
      try {
        body = xhr.responseText ? JSON.parse(xhr.responseText) : null
      } catch {
        body = null
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        onProgress?.(1)
        resolve(body as Job)
      } else {
        reject(errorFromBody(xhr.status, body))
      }
    }
    xhr.onerror = () => reject(new ApiError(0, 'NETWORK_ERROR', NETWORK_ERROR))
    xhr.send(form)
  })
}

/**
 * Download an output file as a Blob. Fetching (instead of a bare `<a href>`) lets us show the
 * Polish `FILE_EXPIRED` / `NOT_FOUND` message instead of saving an error JSON as a file.
 */
export async function downloadBlob(url: string): Promise<Blob> {
  let response: Response
  try {
    response = await fetch(url, { credentials: 'include' })
  } catch {
    throw new ApiError(0, 'NETWORK_ERROR', NETWORK_ERROR)
  }
  if (!response.ok) throw errorFromBody(response.status, await parseJson(response))
  return response.blob()
}
