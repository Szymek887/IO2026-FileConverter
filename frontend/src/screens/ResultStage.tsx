import { useState } from 'react'
import JSZip from 'jszip'
import { ApiError, downloadBlob } from '../api/client'
import type { OutputFileInfo } from '../api/types'
import { Confetti, DownloadIcon, FileIcon } from '../components/Icons'
import { Mascot } from '../components/Mascot'
import { formatBytes, saveBlob } from '../lib/format'
import type { ConversionItem } from '../lib/useConversion'

interface ResultStageProps {
  items: ConversionItem[]
  finished: boolean
  onAgain: () => void
  onUnauthenticated: (message: string) => void
}

const PHASE_LABEL: Record<ConversionItem['phase'], string> = {
  uploading: 'Wysyłanie',
  queued: 'W kolejce…',
  processing: 'Konwertuję…',
  done: '',
  error: '',
}

/** Progress bar fill: upload takes the first 60 %, then queue/processing, then done. */
function progressOf(item: ConversionItem): number {
  switch (item.phase) {
    case 'uploading':
      return Math.round(item.uploadProgress * 60)
    case 'queued':
      return 65
    case 'processing':
      return 85
    default:
      return 100
  }
}

export function ResultStage({ items, finished, onAgain, onUnauthenticated }: ResultStageProps) {
  const [downloadError, setDownloadError] = useState<string | null>(null)
  const [zipping, setZipping] = useState(false)

  const outputs = items.flatMap((i) => i.outputs)
  const failed = items.filter((i) => i.phase === 'error').length
  const allFailed = finished && failed === items.length
  const someFailed = finished && failed > 0 && !allFailed

  const handleError = (e: unknown) => {
    if (e instanceof ApiError && e.code === 'UNAUTHENTICATED') return onUnauthenticated(e.message)
    setDownloadError(e instanceof ApiError ? e.message : 'Nie udało się pobrać pliku.')
  }

  const download = async (output: OutputFileInfo) => {
    setDownloadError(null)
    try {
      saveBlob(await downloadBlob(output.url), output.name)
    } catch (e) {
      handleError(e)
    }
  }

  const downloadAll = async () => {
    setDownloadError(null)
    setZipping(true)
    try {
      const zip = new JSZip()
      const used = new Set<string>()
      for (const output of outputs) {
        let name = output.name
        for (let n = 2; used.has(name); n++) name = output.name.replace(/(\.[^.]+)?$/, ` (${n})$1`)
        used.add(name)
        zip.file(name, await downloadBlob(output.url))
      }
      saveBlob(await zip.generateAsync({ type: 'blob' }), 'konwus.zip')
    } catch (e) {
      handleError(e)
    } finally {
      setZipping(false)
    }
  }

  const title = !finished ? 'Konwertuję…' : allFailed ? 'Nie wyszło…' : 'Gotowe!'
  const bubble = !finished
    ? { text: 'Chwileczkę, mielę pliki… ⚙️', side: 'right' as const }
    : allFailed
      ? { text: 'Ups… coś poszło nie tak 😢', side: 'right' as const }
      : someFailed
        ? { text: 'Prawie wszystko! 😅', side: 'right' as const }
        : undefined

  return (
    <section className="screen screen--result" aria-label={title}>
      {finished && !allFailed && <Confetti />}
      <Mascot
        width={500}
        minHeight={480}
        face={!finished ? 'focus' : allFailed ? 'sad' : 'joy'}
        mood={!finished ? 'busy' : allFailed ? 'idle' : 'cheer'}
        leftArm={finished && !allFailed ? 'cheer' : 'down'}
        rightArm={finished && !allFailed ? 'cheer' : 'down'}
        bubble={bubble}
        className="screen__mascot"
      >
        <div className="result">
          <h2 className="result__title" aria-live="polite">
            {title}
          </h2>
          <ul className="file-list" aria-label="Wyniki konwersji">
            {items.map((item, i) => {
              const output = item.outputs[0]
              const done = item.phase === 'done' && output
              return (
                <li
                  key={item.key}
                  className={`file-card file-card--result is-${item.phase}`}
                  style={{ animationDelay: `${i * 80}ms` }}
                  data-testid="result-card"
                >
                  <FileIcon label={done ? item.target : item.source} variant={done ? 'target' : 'source'} />
                  <div className="file-card__info">
                    <span className="file-card__name" title={done ? output.name : item.fileName}>
                      {done ? output.name : item.fileName}
                    </span>
                    {item.phase === 'error' ? (
                      <span className="file-card__error" role="alert">
                        {item.message}
                      </span>
                    ) : (
                      <span className="file-card__meta">
                        {item.source.toUpperCase()} → {item.target.toUpperCase()} ·{' '}
                        {done ? formatBytes(output.size) : `${PHASE_LABEL[item.phase]}${item.phase === 'uploading' ? ` ${Math.round(item.uploadProgress * 100)}%` : ''}`}
                      </span>
                    )}
                    {item.phase !== 'error' && (
                      <span
                        className={`progress ${item.phase === 'processing' || item.phase === 'queued' ? 'is-working' : ''}`}
                        role="progressbar"
                        aria-label={`Postęp: ${item.fileName}`}
                        aria-valuemin={0}
                        aria-valuemax={100}
                        aria-valuenow={progressOf(item)}
                      >
                        <span className="progress__bar" style={{ width: `${progressOf(item)}%` }} />
                      </span>
                    )}
                  </div>
                  {done && (
                    <button
                      type="button"
                      className="icon-button"
                      aria-label={`Pobierz ${output.name}`}
                      onClick={() => download(output)}
                    >
                      <DownloadIcon />
                    </button>
                  )}
                </li>
              )
            })}
          </ul>

          {downloadError && (
            <p className="form__error" role="alert">
              {downloadError}
            </p>
          )}

          {finished && outputs.length > 1 && (
            <button type="button" className="btn btn--cta btn--wide" onClick={downloadAll} disabled={zipping}>
              {zipping ? 'Pakuję…' : '⤓ Pobierz wszystko (.zip)'}
            </button>
          )}
          {finished && (
            <button type="button" className="link-button link-button--strong" onClick={onAgain}>
              {allFailed ? 'Spróbuj z innymi plikami' : 'Konwertuj kolejne pliki'}
            </button>
          )}
        </div>
      </Mascot>
    </section>
  )
}
