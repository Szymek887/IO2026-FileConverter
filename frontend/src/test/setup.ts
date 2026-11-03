import '@testing-library/jest-dom/vitest'
import { File as NodeFile } from 'node:buffer'
import { cleanup } from '@testing-library/react'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll, beforeEach } from 'vitest'
import { config } from '../config'
import { createHandlers } from '../mocks/handlers'

/** Shared MSW server – the same mock API as `npm run dev:mock`, but fast. */
export const server = setupServer()

export const fastHandlers = (loggedInAs: string | null = null) =>
  createHandlers({ queuedMs: 10, processingMs: 30, loggedInAs })

beforeAll(() => {
  server.listen({ onUnhandledFrame: 'error' })
  config.pollIntervalMs = 20
})

beforeEach(() => {
  server.resetHandlers(...fastHandlers())
})

afterEach(() => cleanup())

afterAll(() => server.close())

/**
 * `File` as jsdom implements it – use it to create files in tests, so jsdom's FormData/XHR accept
 * them. The global `File` is switched to Node's, because Node's multipart parser (behind
 * `request.formData()` in the MSW handlers) builds parsed files with `globalThis.File` and
 * rejects jsdom's class.
 */
export const DomFile = globalThis.File
export const testFile = (name: string, content = 'data') => new DomFile([content], name)
globalThis.File = NodeFile as unknown as typeof File

// jsdom lacks these browser APIs.
if (!URL.createObjectURL) URL.createObjectURL = () => 'blob:mock'
if (!URL.revokeObjectURL) URL.revokeObjectURL = () => {}
