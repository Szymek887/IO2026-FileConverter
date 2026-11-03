import { describe, expect, it } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { demoFormats } from '../demo/formats';
import { useSelectedFiles } from '../hooks/useSelectedFiles';
import { fileKey, getAcceptAttribute, getCommonTargets, getExtension, validateFileSelection } from './files';

function file(name: string, size = 100): File {
  const result = new File(['sample'], name, { lastModified: 123 });
  Object.defineProperty(result, 'size', { value: size });
  return result;
}

describe('Walidacja plików według kontraktu', () => {
  it('normalizuje wielkie litery i aliasy JPEG/HEIF', () => {
    expect(getExtension('ZDJECIE.JPEG', demoFormats.extension_aliases)).toBe('jpg');
    expect(getExtension('zdjecie.HEIF', demoFormats.extension_aliases)).toBe('heic');
    expect(validateFileSelection([], [file('a.JPEG'), file('b.HEIF')], demoFormats)).toMatchObject({ ok: true, commonTargets: ['png'] });
  });
  it('akceptuje dokładnie 250 MiB i odrzuca o jeden bajt więcej', () => {
    expect(validateFileSelection([], [file('a.png', 262_144_000)], demoFormats).ok).toBe(true);
    expect(validateFileSelection([], [file('a.png', 262_144_001)], demoFormats)).toMatchObject({ ok: false, errors: [expect.stringContaining('250 MiB')] });
  });
  it('odrzuca trzeci plik, także dodany osobno', () => {
    expect(validateFileSelection([file('a.png')], [file('b.png'), file('c.png')], demoFormats).ok).toBe(false);
  });
  it('odrzuca pliki bez rozszerzenia i nieobsługiwane PDF', () => {
    expect(validateFileSelection([], [file('a.pdf')], demoFormats).ok).toBe(false);
    expect(validateFileSelection([], [file('plik')], demoFormats).ok).toBe(false);
  });
  it('odrzuca ponowne dodanie tego samego pliku', () => {
    const a = file('a.png');
    expect(validateFileSelection([a], [a], demoFormats)).toMatchObject({ ok: false, errors: [expect.stringContaining('już na liście')] });
  });
  it('wyznacza przecięcie, a nie sumę formatów', () => {
    expect(getCommonTargets([file('a.wav'), file('b.mp3')], demoFormats)).toEqual(['flac']);
    expect(getCommonTargets([], demoFormats)).toEqual([]);
  });
  it('odrzuca obraz i wideo w jednym zleceniu', () => {
    expect(validateFileSelection([], [file('a.mp4'), file('b.png')], demoFormats)).toMatchObject({ ok: false, errors: [expect.stringContaining('wspólnego formatu')] });
  });
  it('czyta limity z konfiguracji API', () => {
    const smaller = { ...demoFormats, max_file_size: 50, max_files_per_job: 1 };
    expect(validateFileSelection([], [file('a.png', 51)], smaller).ok).toBe(false);
    expect(validateFileSelection([], [file('a.png', 10), file('b.png', 10)], smaller).ok).toBe(false);
  });
  it('uwzględnia aliasy również w filtrze wyboru z dysku', () => {
    expect(getAcceptAttribute(demoFormats)).toContain('.jpeg');
    expect(getAcceptAttribute(demoFormats)).toContain('.heif');
  });
  it('zachowuje wcześniejszy wybór po błędnym dodaniu i usuwa wskazany plik', () => {
    const { result } = renderHook(() => useSelectedFiles(demoFormats));
    const a = file('a.png');
    act(() => result.current.addFiles([a]));
    act(() => result.current.addFiles([file('a.pdf')]));
    expect(result.current.files).toEqual([a]);
    expect(result.current.errors).toHaveLength(1);
    act(() => result.current.removeFile(fileKey(a)));
    expect(result.current.files).toHaveLength(0);
    expect(result.current.errors).toHaveLength(0);
  });
  it('nie gubi szybko następujących po sobie dodań', () => {
    const { result } = renderHook(() => useSelectedFiles(demoFormats));
    act(() => {
      result.current.addFiles([file('a.png')]);
      result.current.addFiles([file('b.png')]);
      result.current.addFiles([file('c.png')]);
    });
    expect(result.current.files.map(value => value.name)).toEqual(['a.png', 'b.png']);
    expect(result.current.errors).toHaveLength(1);
  });
});
