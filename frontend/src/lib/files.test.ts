import { describe, expect, it } from 'vitest'
import { MOCK_FORMATS } from '../mocks/handlers'
import { normalizeExtension, validateNewFiles, type SelectedFile } from './files'

const file = (name: string) => new File([new Uint8Array(1)], name, { lastModified: 0 })
const sized = (name: string, size: number) => {
  const f = file(name)
  Object.defineProperty(f, 'size', { value: size })
  return f
}

describe('normalizeExtension', () => {
  it.each([
    ['film.MP4', 'mp4'],
    ['zdjecie.JPEG', 'jpg'],
    ['iphone.heif', 'heic'],
    ['archiwum.tar.gz', 'gz'],
    ['bez_rozszerzenia', ''],
    ['.ukryty', ''],
    ['kropka.', ''],
  ])('%s -> %s', (name, ext) => {
    expect(normalizeExtension(name, MOCK_FORMATS)).toBe(ext)
  })
})

describe('validateNewFiles', () => {
  it('accepts supported files and preselects the first allowed target', () => {
    const result = validateNewFiles([file('a.wav'), file('b.PNG')], [], MOCK_FORMATS)
    expect(result.ok).toBe(true)
    if (!result.ok) return
    expect(result.accepted.map((f) => [f.source, f.target])).toEqual([
      ['wav', 'flac'],
      ['png', 'jpg'],
    ])
  })

  it('rejects an unsupported format', () => {
    expect(validateNewFiles([file('dokument.pdf')], [], MOCK_FORMATS)).toEqual({
      ok: false,
      message: 'Format pliku „dokument.pdf” nie jest obsługiwany.',
    })
  })

  it('rejects more than max_files_per_job, counting already selected files', () => {
    const current = [{ key: 'x' }] as SelectedFile[]
    expect(validateNewFiles([file('a.mp3'), file('b.mp3')], current, MOCK_FORMATS)).toEqual({
      ok: false,
      message: 'Możesz przesłać maksymalnie 2 pliki naraz.',
    })
  })

  it('rejects files over 250 MB but accepts exactly 250 MB', () => {
    expect(validateNewFiles([sized('duzy.mov', 262_144_001)], [], MOCK_FORMATS)).toEqual({
      ok: false,
      message: 'Plik „duzy.mov” przekracza maksymalny rozmiar 250 MB.',
    })
    expect(validateNewFiles([sized('ok.mov', 262_144_000)], [], MOCK_FORMATS).ok).toBe(true)
  })

  it('rejects empty files', () => {
    expect(validateNewFiles([sized('pusty.mp3', 0)], [], MOCK_FORMATS).ok).toBe(false)
  })

  it('rejects an empty selection', () => {
    expect(validateNewFiles([], [], MOCK_FORMATS)).toEqual({ ok: false, message: 'Nie wybrano żadnego pliku.' })
  })
})
