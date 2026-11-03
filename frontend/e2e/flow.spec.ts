import { expect, test } from '@playwright/test'
import { file, login, MOCK_CODE, openPicker } from './helpers'

test.describe('logowanie', () => {
  test('pokazuje błąd dla niepoprawnego e-maila', async ({ page }) => {
    await page.goto('/')
    await page.getByLabel('Adres e-mail').fill('to-nie-email')
    await page.getByRole('button', { name: 'Dalej →' }).click()
    await expect(page.getByRole('alert')).toHaveText('Podaj poprawny adres e-mail.')
  })

  test('błędny kod, potem poprawny – logowanie i wylogowanie', async ({ page }) => {
    await page.goto('/')
    await page.getByLabel('Adres e-mail').fill('jan.kowalski@example.com')
    await page.getByRole('button', { name: 'Dalej →' }).click()

    await expect(page.getByText('jan***@example.com')).toBeVisible()
    await expect(page.getByRole('button', { name: /Wyślij ponownie \(\d+ s\)/ })).toBeDisabled()

    await page.getByLabel('Kod logowania z e-maila').fill('000000')
    await page.getByRole('button', { name: 'Zaloguj' }).click()
    await expect(page.getByRole('alert')).toHaveText('Nieprawidłowy kod logowania.')

    await page.getByLabel('Kod logowania z e-maila').fill(MOCK_CODE)
    await page.getByRole('button', { name: 'Zaloguj' }).click()
    await expect(page.getByRole('button', { name: 'KONWERTUJ' })).toBeVisible()

    // Session survives a reload (GET /auth/me)
    await page.reload()
    await expect(page.getByRole('button', { name: 'KONWERTUJ' })).toBeVisible()

    await page.getByRole('button', { name: 'Wyloguj' }).click()
    await expect(page.getByRole('heading', { name: 'Zaloguj się, aby konwertować pliki' })).toBeVisible()
  })

  test('"Zmień email" wraca do kroku 1', async ({ page }) => {
    await page.goto('/')
    await page.getByLabel('Adres e-mail').fill('ola@example.com')
    await page.getByRole('button', { name: 'Dalej →' }).click()
    await page.getByRole('button', { name: '← Zmień email' }).click()
    await expect(page.getByText('Krok 1 z 2')).toBeVisible()
  })
})

test.describe('konwersja', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
    await openPicker(page)
  })

  test('dwa pliki z różnymi formatami → pobieranie pojedyncze i ZIP', async ({ page }) => {
    await page.getByTestId('file-input').setInputFiles([file('wakacje_2026.mp4', 50_000), file('plaza.png', 6_000)])

    await expect(page.getByText('2 / 2 pliki')).toBeVisible()
    await expect(page.getByText('Dwa naraz? Luz! 💪')).toBeVisible()

    // Targets come from GET /formats (mp4 -> gif/mov, png -> jpg/heic)
    const mp4Target = page.getByLabel('Format docelowy dla wakacje_2026.mp4')
    await expect(mp4Target.locator('option')).toHaveText(['GIF', 'MOV'])
    await mp4Target.selectOption('mov')
    await page.getByLabel('Format docelowy dla plaza.png').selectOption('jpg')

    await page.getByRole('button', { name: 'Konwertuj 2 pliki ▶' }).click()
    await expect(page.getByRole('heading', { name: 'Konwertuję…' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Gotowe!' })).toBeVisible({ timeout: 15_000 })

    await expect(page.getByText('wakacje_2026.mov')).toBeVisible()
    await expect(page.getByText('plaza.jpg')).toBeVisible()

    const single = page.waitForEvent('download')
    await page.getByRole('button', { name: 'Pobierz plaza.jpg' }).click()
    expect((await single).suggestedFilename()).toBe('plaza.jpg')

    const zip = page.waitForEvent('download')
    await page.getByRole('button', { name: /Pobierz wszystko/ }).click()
    expect((await zip).suggestedFilename()).toBe('konwus.zip')

    await page.getByRole('button', { name: 'Konwertuj kolejne pliki' }).click()
    await expect(page.getByText('0 / 2 pliki')).toBeVisible()
  })

  test('drag & drop pliku', async ({ page }) => {
    const dataTransfer = await page.evaluateHandle(() => {
      const dt = new DataTransfer()
      dt.items.add(new File([new Uint8Array(4096)], 'nagranie.wav', { type: 'audio/wav' }))
      return dt
    })
    const zone = page.getByTestId('dropzone')
    await zone.dispatchEvent('dragenter', { dataTransfer })
    await expect(page.getByText('Puszczaj! 😮')).toBeVisible()
    await zone.dispatchEvent('drop', { dataTransfer })

    await expect(page.getByText('nagranie.wav')).toBeVisible()
    await expect(page.getByText('1 / 2 pliki')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Konwertuj 1 plik ▶' })).toBeVisible()
  })

  test('odrzuca nieobsługiwany format i więcej niż 2 pliki', async ({ page }) => {
    await page.getByTestId('file-input').setInputFiles([file('dokument.pdf')])
    await expect(page.getByRole('alert')).toHaveText('Format pliku „dokument.pdf” nie jest obsługiwany.')

    await page.getByTestId('file-input').setInputFiles([file('a.mp3'), file('b.mp3'), file('c.mp3')])
    await expect(page.getByRole('alert')).toHaveText('Możesz przesłać maksymalnie 2 pliki naraz.')
  })

  test('usuwanie pliku wraca do strefy upuszczania', async ({ page }) => {
    await page.getByTestId('file-input').setInputFiles([file('foto.JPEG')])
    await expect(page.getByText('foto.JPEG')).toBeVisible()
    // alias jpeg -> jpg
    await expect(page.getByLabel('Format docelowy dla foto.JPEG').locator('option')).toHaveText(['PNG', 'HEIC'])
    await page.getByRole('button', { name: 'Usuń foto.JPEG' }).click()
    await expect(page.getByTestId('dropzone')).toBeVisible()
  })

  test('błąd konwersji i błąd walidacji backendu są pokazywane przy plikach', async ({ page }) => {
    await page.getByTestId('file-input').setInputFiles([file('blad.mp3'), file('uszkodzony.png')])
    await page.getByRole('button', { name: 'Konwertuj 2 pliki ▶' }).click()

    await expect(page.getByText('Nie udało się przekonwertować pliku „blad.mp3”.')).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText(/Plik „uszkodzony.png” jest uszkodzony/)).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Nie wyszło…' })).toBeVisible()
    await expect(page.getByRole('button', { name: /Pobierz wszystko/ })).toHaveCount(0)
  })
})
