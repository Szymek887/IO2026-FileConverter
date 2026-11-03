/** Human readable size in Polish notation: `48,2 MB`, `512 KB`, `12 B`. */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  const units = ['KB', 'MB', 'GB']
  let value = bytes / 1024
  let unit = 0
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024
    unit++
  }
  const rounded = value >= 100 ? Math.round(value).toString() : value.toFixed(1).replace('.', ',')
  return `${rounded} ${units[unit]}`
}

/** `jan.kowalski@mail.com` -> `jan***@mail.com` (as on the login design). */
export function maskEmail(email: string): string {
  const at = email.lastIndexOf('@')
  if (at <= 0) return email
  const local = email.slice(0, at)
  const visible = local.slice(0, Math.min(3, Math.max(1, local.length - 1)))
  return `${visible}***${email.slice(at)}`
}

/** Polish plural for "plik": 1 plik, 2–4 pliki, 5+ plików. */
export function pluralFiles(count: number): string {
  if (count === 1) return 'plik'
  const lastTwo = count % 100
  const last = count % 10
  if (last >= 2 && last <= 4 && (lastTwo < 12 || lastTwo > 14)) return 'pliki'
  return 'plików'
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
export const isValidEmail = (email: string) => EMAIL_RE.test(email.trim())

/** Triggers a browser download of a Blob under the given file name. */
export function saveBlob(blob: Blob, fileName: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = fileName
  link.rel = 'noopener'
  document.body.appendChild(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 10_000)
}
