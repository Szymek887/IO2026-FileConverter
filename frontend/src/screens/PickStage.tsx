import { useRef, useState, type DragEvent } from 'react'
import type { Format, FormatsResponse } from '../api/types'
import { FileIcon, UploadIcon } from '../components/Icons'
import { Mascot } from '../components/Mascot'
import { allFormats, categoryLabel, validateNewFiles, type SelectedFile } from '../lib/files'
import { formatBytes, pluralFiles } from '../lib/format'

interface PickStageProps {
  formats: FormatsResponse
  files: SelectedFile[]
  onFilesChange: (files: SelectedFile[]) => void
  onConvert: () => void
}

/** Drag & drop (design 3) and the per-file target format picker (design 4). */
export function PickStage({ formats, files, onFilesChange, onConvert }: PickStageProps) {
  const [error, setError] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const [shake, setShake] = useState(0)
  const input = useRef<HTMLInputElement>(null)
  const dragDepth = useRef(0)

  const limit = formats.max_files_per_job
  const hasFiles = files.length > 0
  const canAddMore = files.length < limit
  const accept = allFormats(formats)
    .concat(Object.keys(formats.extension_aliases) as Format[])
    .map((f) => `.${f}`)
    .join(',')

  const addFiles = (incoming: File[]) => {
    const result = validateNewFiles(incoming, files, formats)
    if (!result.ok) {
      setError(result.message)
      setShake((n) => n + 1)
      return
    }
    setError(null)
    onFilesChange([...files, ...result.accepted])
  }

  const removeFile = (key: string) => {
    setError(null)
    onFilesChange(files.filter((f) => f.key !== key))
  }

  const setTarget = (key: string, target: Format) =>
    onFilesChange(files.map((f) => (f.key === key ? { ...f, target } : f)))

  const onDragEnter = (event: DragEvent) => {
    if (!event.dataTransfer.types.includes('Files')) return
    event.preventDefault()
    dragDepth.current++
    setDragging(true)
  }
  const onDragOver = (event: DragEvent) => {
    if (!event.dataTransfer.types.includes('Files')) return
    event.preventDefault()
    event.dataTransfer.dropEffect = canAddMore ? 'copy' : 'none'
  }
  const onDragLeave = () => {
    dragDepth.current = Math.max(0, dragDepth.current - 1)
    if (dragDepth.current === 0) setDragging(false)
  }
  const onDrop = (event: DragEvent) => {
    event.preventDefault()
    dragDepth.current = 0
    setDragging(false)
    addFiles(Array.from(event.dataTransfer.files))
  }

  const bubbleText = error
    ? 'Ups! Tego nie przełknę 😬'
    : dragging
      ? 'Puszczaj! 😮'
      : files.length === 0
        ? 'Dawaj pliki! 📂📂'
        : files.length === 1
          ? 'Mniam! Wybierz format 👇'
          : 'Dwa naraz? Luz! 💪'

  const formatList = allFormats(formats)
    .map((f) => f.toUpperCase())
    .join(' · ')

  return (
    <section
      className={`screen screen--pick ${dragging ? 'is-dragging' : ''}`}
      aria-label={hasFiles ? 'Wybór formatu' : 'Dodaj pliki'}
      onDragEnter={onDragEnter}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
    >
      <Mascot
        width={hasFiles ? 580 : 520}
        minHeight={480}
        face={error ? 'sad' : dragging ? 'surprised' : 'focus'}
        leftArm="down"
        rightArm={files.length === limit ? 'raised' : 'down'}
        bubble={{ text: bubbleText, side: 'right' }}
        shakeKey={shake}
        className="screen__mascot"
      >
        <div className="pick">
          <div className="counter" aria-label={`Wybrano ${files.length} z ${limit} plików`}>
            {Array.from({ length: limit }, (_, i) => (
              <span key={i} className={`counter__dot ${i < files.length ? 'is-filled' : ''}`} />
            ))}
            <span className="counter__label">
              {files.length} / {limit} {pluralFiles(limit)}
            </span>
          </div>

          {!hasFiles && (
            <div
              className={`dropzone ${dragging ? 'is-active' : ''}`}
              role="button"
              tabIndex={0}
              aria-label="Przeciągnij i upuść pliki lub kliknij, aby wybrać"
              onClick={() => input.current?.click()}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  input.current?.click()
                }
              }}
              data-testid="dropzone"
            >
              <UploadIcon />
              <p className="dropzone__title">Przeciągnij i upuść maks. {limit} pliki</p>
              <p className="dropzone__formats">{formatList}</p>
            </div>
          )}

          {hasFiles && (
            <ul className="file-list" aria-label="Wybrane pliki">
              {files.map((f, i) => (
                <li key={f.key} className="file-card" style={{ animationDelay: `${i * 80}ms` }}>
                  <FileIcon label={f.source} variant="source" />
                  <div className="file-card__info">
                    <span className="file-card__name" title={f.file.name}>
                      {f.file.name}
                    </span>
                    <span className="file-card__meta">
                      {categoryLabel(f.source, formats)} · {formatBytes(f.file.size)}
                    </span>
                  </div>
                  <div className="file-card__formats">
                    <span className="pill pill--source">{f.source.toUpperCase()}</span>
                    <span className="file-card__arrow" aria-hidden="true">
                      →
                    </span>
                    <span className="pill pill--target pill--select">
                      <select
                        aria-label={`Format docelowy dla ${f.file.name}`}
                        value={f.target}
                        onChange={(e) => setTarget(f.key, e.target.value as Format)}
                      >
                        {formats.conversions[f.source].map((t) => (
                          <option key={t} value={t}>
                            {t.toUpperCase()}
                          </option>
                        ))}
                      </select>
                    </span>
                  </div>
                  <button
                    type="button"
                    className="file-card__remove"
                    aria-label={`Usuń ${f.file.name}`}
                    onClick={() => removeFile(f.key)}
                  >
                    ×
                  </button>
                </li>
              ))}
            </ul>
          )}

          {error && (
            <p className="form__error pick__error" role="alert">
              {error}
            </p>
          )}

          <input
            ref={input}
            type="file"
            multiple={canAddMore && limit - files.length > 1}
            accept={accept}
            className="visually-hidden"
            data-testid="file-input"
            aria-label="Wybierz pliki"
            tabIndex={-1}
            onChange={(e) => {
              addFiles(Array.from(e.target.files ?? []))
              e.target.value = ''
            }}
          />

          {!hasFiles && (
            <>
              <p className="pick__or">lub</p>
              <button type="button" className="btn btn--cta" onClick={() => input.current?.click()}>
                ⤒ Import
              </button>
            </>
          )}

          {hasFiles && (
            <>
              {files.length > 1 && <p className="pick__hint">Każdy plik może mieć inny format docelowy</p>}
              {canAddMore && (
                <button type="button" className="link-button link-button--strong" onClick={() => input.current?.click()}>
                  + Dodaj drugi plik
                </button>
              )}
              <button type="button" className="btn btn--cta btn--wide" onClick={onConvert}>
                Konwertuj {files.length} {pluralFiles(files.length)} ▶
              </button>
            </>
          )}
        </div>
      </Mascot>
    </section>
  )
}
