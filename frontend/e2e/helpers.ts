import { expect, type Page } from '@playwright/test'

export const MOCK_CODE = '123456'

/** A small in-memory file for `setInputFiles`. */
export const file = (name: string, size = 2048, mimeType = 'application/octet-stream') => ({
  name,
  mimeType,
  buffer: Buffer.alloc(size, 7),
})

export async function login(page: Page, email = 'jan.kowalski@example.com') {
  await page.goto('/')
  await page.getByLabel('Adres e-mail').fill(email)
  await page.getByRole('button', { name: 'Dalej →' }).click()
  await expect(page.getByText('Krok 2 z 2')).toBeVisible()
  await page.getByLabel('Kod logowania z e-maila').fill(MOCK_CODE)
  await page.getByRole('button', { name: 'Zaloguj' }).click()
  await expect(page.getByRole('button', { name: 'KONWERTUJ' })).toBeVisible()
}

export async function openPicker(page: Page) {
  await page.getByRole('button', { name: 'KONWERTUJ' }).click()
  await expect(page.getByText(/Przeciągnij i upuść/)).toBeVisible()
}
