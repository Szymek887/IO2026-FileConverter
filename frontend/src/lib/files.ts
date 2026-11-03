import type { Category, Format, FormatsResponse } from '../api/types'

/** Extension from the file name, lowercase, aliases normalized (`.JPEG` -> `jpg`). */
export function normalizeExtension(fileName: string, formats: FormatsResponse): string {
  const dot = fileName.lastIndexOf('.')
  if (dot <= 0 || dot === fileName.length - 1) return ''
  const ext = fileName.slice(dot + 1).toLowerCase()
  return formats.extension_aliases[ext] ?? ext
}

export function isSupportedFormat(ext: string, formats: FormatsResponse): ext is Format {
  return Object.prototype.hasOwnProperty.call(formats.conversions, ext)
}

export function categoryOf(format: Format, formats: FormatsResponse): Category | undefined {
  return formats.categories.find((c) => c.formats.includes(format))?.id
}

export function categoryLabel(format: Format, formats: FormatsResponse): string {
  return formats.categories.find((c) => c.formats.includes(format))?.label ?? ''
}

/** All formats in the order the API lists them. */
export function allFormats(formats: FormatsResponse): Format[] {
  return formats.categories.flatMap((c) => c.formats)
}

export interface SelectedFile {
  /** Stable key for React lists. */
  key: string
  file: File
  source: Format
  target: Format
}

export type ValidationResult =
  | { ok: true; accepted: SelectedFile[] }
  | { ok: false; message: string }

let keyCounter = 0
const nextKey = () => `f${Date.now().toString(36)}-${(keyCounter++).toString(36)}`

const mb = (bytes: number) => Math.round(bytes / (1024 * 1024))

/**
 * Client-side pre-validation of newly picked files (contract §7). Messages mirror the
 * backend's Polish texts; the backend still performs the final check on upload.
 */
export function validateNewFiles(
  incoming: File[],
  current: SelectedFile[],
  formats: FormatsResponse,
): ValidationResult {
  if (incoming.length === 0) return { ok: false, message: 'Nie wybrano żadnego pliku.' }

  const limit = formats.max_files_per_job
  if (current.length + incoming.length > limit) {
    return { ok: false, message: `Możesz przesłać maksymalnie ${limit} pliki naraz.` }
  }

  const accepted: SelectedFile[] = []
  for (const file of incoming) {
    const ext = normalizeExtension(file.name, formats)
    if (!isSupportedFormat(ext, formats)) {
      return { ok: false, message: `Format pliku „${file.name}” nie jest obsługiwany.` }
    }
    if (file.size > formats.max_file_size) {
      return {
        ok: false,
        message: `Plik „${file.name}” przekracza maksymalny rozmiar ${mb(formats.max_file_size)} MB.`,
      }
    }
    if (file.size === 0) {
      return { ok: false, message: `Plik „${file.name}” jest pusty.` }
    }
    const targets = formats.conversions[ext]
    if (!targets || targets.length === 0) {
      return { ok: false, message: `Format pliku „${file.name}” nie jest obsługiwany.` }
    }
    accepted.push({ key: nextKey(), file, source: ext, target: targets[0] })
  }
  return { ok: true, accepted }
}
