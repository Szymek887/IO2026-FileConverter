import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, createJob, getJob } from '../api/client'
import type { Format, OutputFileInfo } from '../api/types'
import { config } from '../config'
import type { SelectedFile } from './files'

export type ItemPhase = 'uploading' | 'queued' | 'processing' | 'done' | 'error'

export interface ConversionItem {
  key: string
  fileName: string
  source: Format
  target: Format
  size: number
  phase: ItemPhase
  /** 0–1 while uploading. */
  uploadProgress: number
  outputs: OutputFileInfo[]
  /** Polish message from the API on error. */
  message?: string
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

/**
 * Converts each selected file as its own job (`POST /api/jobs` with one file), so every file can
 * have a different target format as on the design. Then polls `GET /api/jobs/{id}` until the job
 * is `done` or `error`.
 */
export function useConversion(onUnauthenticated: (message: string) => void) {
  const [items, setItems] = useState<ConversionItem[]>([])
  const runId = useRef(0)

  useEffect(
    () => () => {
      runId.current++ // stop polling on unmount
    },
    [],
  )

  const update = (run: number, key: string, patch: Partial<ConversionItem>) => {
    if (run !== runId.current) return
    setItems((list) => list.map((item) => (item.key === key ? { ...item, ...patch } : item)))
  }

  const convertOne = async (run: number, selected: SelectedFile) => {
    const { key } = selected
    try {
      let job = await createJob([selected.file], selected.target, (fraction) =>
        update(run, key, { uploadProgress: fraction }),
      )
      update(run, key, { phase: job.status === 'processing' ? 'processing' : 'queued', uploadProgress: 1 })
      while (job.status === 'queued' || job.status === 'processing') {
        await sleep(config.pollIntervalMs)
        if (run !== runId.current) return
        job = await getJob(job.id)
        if (job.status === 'queued' || job.status === 'processing') update(run, key, { phase: job.status })
      }
      if (job.status === 'done' && job.result) {
        update(run, key, { phase: 'done', outputs: job.result.output_files, message: job.result.message })
      } else {
        update(run, key, {
          phase: 'error',
          message: job.result?.message ?? `Nie udało się przekonwertować pliku „${selected.file.name}”.`,
        })
      }
    } catch (e) {
      const err = e instanceof ApiError ? e : null
      if (err?.code === 'UNAUTHENTICATED') {
        if (run === runId.current) onUnauthenticated(err.message)
        return
      }
      update(run, key, { phase: 'error', message: err?.message ?? 'Wystąpił nieoczekiwany błąd.' })
    }
  }

  const start = useCallback(
    (selected: SelectedFile[]) => {
      const run = ++runId.current
      setItems(
        selected.map((s) => ({
          key: s.key,
          fileName: s.file.name,
          source: s.source,
          target: s.target,
          size: s.file.size,
          phase: 'uploading',
          uploadProgress: 0,
          outputs: [],
        })),
      )
      for (const s of selected) void convertOne(run, s)
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [onUnauthenticated],
  )

  const reset = useCallback(() => {
    runId.current++
    setItems([])
  }, [])

  const finished = items.length > 0 && items.every((i) => i.phase === 'done' || i.phase === 'error')
  return { items, start, reset, finished }
}
