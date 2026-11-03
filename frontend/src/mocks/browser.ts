import { setupWorker } from 'msw/browser'
import { createHandlers } from './handlers'

/** Starts the in-browser mock API (`npm run dev:mock`). */
export async function startMockApi(): Promise<void> {
  const worker = setupWorker(...createHandlers({ persistSession: true, latencyMs: 250 }))
  await worker.start({
    onUnhandledFrame: 'bypass',
    quiet: true,
  })
  console.info('%c[mock] API mock aktywny – kod logowania: 123456', 'color:#2F7A74;font-weight:bold')
}
