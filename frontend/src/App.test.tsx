import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { describe, expect, it, vi } from 'vitest'
import App from './App'
import * as format from './lib/format'
import { fastHandlers, server, testFile } from './test/setup'

const user = () => userEvent.setup({ applyAccept: false })
const file = (name: string) => testFile(name)

function renderLoggedIn() {
  server.resetHandlers(...fastHandlers('jan@example.com'))
  render(<App />)
}

describe('logowanie', () => {
  it('prowadzi przez e-mail i kod do ekranu konwersji', async () => {
    const u = user()
    render(<App />)

    await u.type(await screen.findByLabelText('Adres e-mail'), 'jan.kowalski@example.com')
    await u.click(screen.getByRole('button', { name: 'Dalej →' }))

    expect(await screen.findByText('Krok 2 z 2')).toBeInTheDocument()
    expect(screen.getByText('jan***@example.com')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Wyślij ponownie \(60 s\)/ })).toBeDisabled()

    await u.type(screen.getByLabelText('Kod logowania z e-maila'), '123456')
    await u.click(screen.getByRole('button', { name: 'Zaloguj' }))

    expect(await screen.findByRole('button', { name: 'KONWERTUJ' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Zalogowano jako jan.kowalski@example.com' })).toBeInTheDocument()
  })

  it('pokazuje komunikat backendu przy złym kodzie', async () => {
    const u = user()
    render(<App />)
    await u.type(await screen.findByLabelText('Adres e-mail'), 'jan@example.com')
    await u.click(screen.getByRole('button', { name: 'Dalej →' }))
    await u.type(await screen.findByLabelText('Kod logowania z e-maila'), '999999')
    await u.click(screen.getByRole('button', { name: 'Zaloguj' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Nieprawidłowy kod logowania.')
  })

  it('waliduje długość kodu po stronie klienta', async () => {
    const u = user()
    render(<App />)
    await u.type(await screen.findByLabelText('Adres e-mail'), 'jan@example.com')
    await u.click(screen.getByRole('button', { name: 'Dalej →' }))
    const input = await screen.findByLabelText('Kod logowania z e-maila')
    await u.type(input, '12ab3')
    expect(input).toHaveValue('123') // only digits
    await u.click(screen.getByRole('button', { name: 'Zaloguj' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Kod logowania składa się z 6 cyfr.')
  })

  it('pokazuje limit użytkowników (503 USER_LIMIT_REACHED)', async () => {
    server.use(
      http.post('*/api/auth/verify-otp', () =>
        HttpResponse.json(
          {
            status: 'error',
            code: 'USER_LIMIT_REACHED',
            message: 'Osiągnięto limit 10 jednocześnie zalogowanych użytkowników. Spróbuj ponownie później.',
            details: null,
          },
          { status: 503 },
        ),
      ),
    )
    const u = user()
    render(<App />)
    await u.type(await screen.findByLabelText('Adres e-mail'), 'jan@example.com')
    await u.click(screen.getByRole('button', { name: 'Dalej →' }))
    await u.type(await screen.findByLabelText('Kod logowania z e-maila'), '123456')
    await u.click(screen.getByRole('button', { name: 'Zaloguj' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/limit 10 jednocześnie zalogowanych/)
  })

  it('automatycznie loguje przy istniejącej sesji i wylogowuje', async () => {
    const u = user()
    renderLoggedIn()
    await u.click(await screen.findByRole('button', { name: 'Wyloguj' }))
    expect(await screen.findByRole('heading', { name: 'Zaloguj się, aby konwertować pliki' })).toBeInTheDocument()
  })
})

describe('konwersja', () => {
  it('konwertuje dwa pliki do różnych formatów i pobiera wynik', async () => {
    const save = vi.spyOn(format, 'saveBlob').mockImplementation(() => {})
    const u = user()
    renderLoggedIn()

    await u.click(await screen.findByRole('button', { name: 'KONWERTUJ' }))
    await u.upload(await screen.findByTestId('file-input'), [file('nagranie.wav'), file('plaza.png')])

    expect(screen.getByText('2 / 2 pliki')).toBeInTheDocument()
    const wavTarget = screen.getByLabelText('Format docelowy dla nagranie.wav')
    expect(within(wavTarget).getAllByRole('option').map((o) => o.textContent)).toEqual(['FLAC', 'MP3'])
    await u.selectOptions(wavTarget, 'mp3')
    await u.selectOptions(screen.getByLabelText('Format docelowy dla plaza.png'), 'heic')

    await u.click(screen.getByRole('button', { name: 'Konwertuj 2 pliki ▶' }))

    expect(await screen.findByRole('heading', { name: 'Gotowe!' })).toBeInTheDocument()
    expect(screen.getByText('nagranie.mp3')).toBeInTheDocument()
    expect(screen.getByText('plaza.heic')).toBeInTheDocument()

    await u.click(screen.getByRole('button', { name: 'Pobierz nagranie.mp3' }))
    await vi.waitFor(() => expect(save).toHaveBeenCalledWith(expect.any(Blob), 'nagranie.mp3'))

    await u.click(screen.getByRole('button', { name: /Pobierz wszystko/ }))
    await vi.waitFor(() => expect(save).toHaveBeenCalledWith(expect.any(Blob), 'konwus.zip'))
    save.mockRestore()
  })

  it('pokazuje błąd konwersji z result.message', async () => {
    const u = user()
    renderLoggedIn()
    await u.click(await screen.findByRole('button', { name: 'KONWERTUJ' }))
    await u.upload(await screen.findByTestId('file-input'), [file('blad.mp3')])
    await u.click(screen.getByRole('button', { name: 'Konwertuj 1 plik ▶' }))
    expect(await screen.findByText('Nie udało się przekonwertować pliku „blad.mp3”.')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Nie wyszło…' })).toBeInTheDocument()
  })

  it('pokazuje komunikat FILE_EXPIRED przy pobieraniu wygasłego pliku', async () => {
    const u = user()
    renderLoggedIn()
    server.use(
      http.get('*/api/jobs/:id/files/:index', () =>
        HttpResponse.json(
          { status: 'error', code: 'FILE_EXPIRED', message: 'Plik wynikowy wygasł. Wykonaj konwersję ponownie.', details: null },
          { status: 410 },
        ),
      ),
    )
    await u.click(await screen.findByRole('button', { name: 'KONWERTUJ' }))
    await u.upload(await screen.findByTestId('file-input'), [file('foto.jpg')])
    await u.click(screen.getByRole('button', { name: 'Konwertuj 1 plik ▶' }))
    await u.click(await screen.findByRole('button', { name: 'Pobierz foto.png' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Plik wynikowy wygasł. Wykonaj konwersję ponownie.')
  })

  it('odrzuca nieobsługiwany plik przed wysłaniem', async () => {
    const u = user()
    renderLoggedIn()
    await u.click(await screen.findByRole('button', { name: 'KONWERTUJ' }))
    await u.upload(await screen.findByTestId('file-input'), [file('notatki.txt')])
    expect(screen.getByRole('alert')).toHaveTextContent('Format pliku „notatki.txt” nie jest obsługiwany.')
    expect(screen.getByText('0 / 2 pliki')).toBeInTheDocument()
  })

  it('wraca do logowania, gdy sesja wygaśnie w trakcie pracy', async () => {
    const u = user()
    renderLoggedIn()
    await u.click(await screen.findByRole('button', { name: 'KONWERTUJ' }))
    await u.upload(await screen.findByTestId('file-input'), [file('glos.flac')])
    server.use(
      http.post('*/api/jobs', () =>
        HttpResponse.json(
          { status: 'error', code: 'UNAUTHENTICATED', message: 'Sesja wygasła. Zaloguj się ponownie.', details: null },
          { status: 401 },
        ),
      ),
    )
    await u.click(screen.getByRole('button', { name: 'Konwertuj 1 plik ▶' }))
    expect(await screen.findByText('Sesja wygasła. Zaloguj się ponownie.')).toBeInTheDocument()
    expect(screen.getByLabelText('Adres e-mail')).toBeInTheDocument()
  })
})
