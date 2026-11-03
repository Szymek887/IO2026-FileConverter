import { describe, expect, it } from 'vitest'
import { formatBytes, isValidEmail, maskEmail, pluralFiles } from './format'

describe('formatBytes', () => {
  it.each([
    [512, '512 B'],
    [2048, '2,0 KB'],
    [6_396_314, '6,1 MB'],
    [50_541_773, '48,2 MB'],
    [262_144_000, '250 MB'],
    [3 * 1024 ** 3, '3,0 GB'],
  ])('%d -> %s', (bytes, text) => expect(formatBytes(bytes)).toBe(text))
})

describe('maskEmail', () => {
  it('keeps three characters of the local part', () => {
    expect(maskEmail('jan.kowalski@mail.com')).toBe('jan***@mail.com')
  })
  it('never reveals a short local part completely', () => {
    expect(maskEmail('ab@x.pl')).toBe('a***@x.pl')
  })
})

describe('pluralFiles', () => {
  it.each([
    [1, 'plik'],
    [2, 'pliki'],
    [4, 'pliki'],
    [5, 'plików'],
    [12, 'plików'],
    [22, 'pliki'],
  ])('%d %s', (n, word) => expect(pluralFiles(n)).toBe(word))
})

describe('isValidEmail', () => {
  it('accepts a normal address and rejects garbage', () => {
    expect(isValidEmail(' jan@example.com ')).toBe(true)
    expect(isValidEmail('jan@')).toBe(false)
    expect(isValidEmail('jan example.com')).toBe(false)
  })
})
