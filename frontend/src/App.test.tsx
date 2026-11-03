import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { demoFormats } from './demo/formats';
import { SESSION_EXPIRED_EVENT } from './api/client';

const session = { email: 'test@example.com', session_expires: Math.floor(Date.now() / 1000) + 3600 };
const anonymous = { status: 'error', code: 'UNAUTHENTICATED', message: 'Sesja wygasła.' };
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

function mockBackend(authenticated = false) {
  const fetchMock = vi.fn(async (url: string, init: RequestInit) => {
    if (url.endsWith('/auth/me')) return authenticated ? json(session) : json(anonymous, 401);
    if (url.endsWith('/auth/request-otp')) return json({ status: 'ok', message: 'Wysłano kod.', otp_expires: Math.floor(Date.now() / 1000) + 600, resend_available_in: 60 }, 202);
    if (url.endsWith('/auth/verify-otp')) {
      const body = JSON.parse(init.body as string);
      if (body.code === '012345') { authenticated = true; return json(session); }
      return json({ status: 'error', code: 'INVALID_OTP', message: 'Nieprawidłowy kod logowania.' }, 401);
    }
    if (url.endsWith('/auth/logout')) { authenticated = false; return new Response(null, { status: 204 }); }
    if (url.endsWith('/formats')) return json(demoFormats);
    throw new Error(`Nieoczekiwane żądanie: ${url}`);
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

describe('Ekrany i integracja osoby A', () => {
  it('prowadzi od e-maila przez OTP z zerem na początku do importu i wylogowania', async () => {
    const user = userEvent.setup();
    const backend = mockBackend();
    render(<App />);
    await user.type(await screen.findByLabelText('Twój adres e-mail'), 'test@example.com');
    await user.click(screen.getByRole('button', { name: /Wyślij kod logowania/ }));
    const otp = await screen.findByLabelText('6-cyfrowy kod');
    await user.type(otp, '111111');
    await user.click(screen.getByRole('button', { name: /Zaloguj się/ }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Nieprawidłowy kod');
    expect(window.location.pathname).toBe('/verify');
    await user.clear(otp); await user.type(otp, '012345');
    await user.click(screen.getByRole('button', { name: /Zaloguj się/ }));
    const input = await screen.findByLabelText('Wybierz pliki');
    await user.upload(input, new File(['data'], 'zdjecie.JPEG', { type: 'image/jpeg' }));
    expect(await screen.findByText('zdjecie.JPEG')).toBeInTheDocument();
    expect(backend.mock.calls.some(([url, init]) => url.endsWith('/auth/verify-otp') && JSON.parse(init.body as string).code === '012345')).toBe(true);
    await user.click(screen.getByRole('button', { name: /Wyloguj/ }));
    expect(await screen.findByLabelText('Twój adres e-mail')).toBeInTheDocument();
    expect(screen.queryByText('zdjecie.JPEG')).not.toBeInTheDocument();
  });
  it('odtwarza sesję bez ponownego OTP', async () => {
    mockBackend(true); render(<App />);
    expect(await screen.findByLabelText('Wybierz pliki')).toBeInTheDocument();
    expect(screen.queryByLabelText('Twój adres e-mail')).not.toBeInTheDocument();
  });
  it('odtwarza ekran OTP i pozostały cooldown po odświeżeniu', async () => {
    mockBackend();
    sessionStorage.setItem('konwus:pending-otp', JSON.stringify({ email: 'test@example.com', expiresAt: Date.now() + 300_000, resendAt: Date.now() + 40_000 }));
    window.history.replaceState({}, '', '/verify');
    render(<App />);
    expect(await screen.findByLabelText('6-cyfrowy kod')).toBeInTheDocument();
    const resend = screen.getByRole('button', { name: /Wyślij ponownie za/ });
    expect(resend).toBeDisabled();
    expect(resend).not.toHaveTextContent('60 s');
  });
  it('pozwala poprosić o nowy kod, gdy poprzedni wygasł', async () => {
    const user = userEvent.setup();
    mockBackend();
    sessionStorage.setItem('konwus:pending-otp', JSON.stringify({ email: 'test@example.com', expiresAt: Date.now() - 1000, resendAt: Date.now() - 1000 }));
    window.history.replaceState({}, '', '/verify'); render(<App />);
    expect(await screen.findByLabelText('6-cyfrowy kod')).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Wyślij kod ponownie' }));
    expect(await screen.findByText('Wysłaliśmy nowy kod. Sprawdź pocztę.')).toBeInTheDocument();
    expect(screen.getByLabelText('6-cyfrowy kod')).toBeEnabled();
  });
  it('przekierowuje z /verify bez e-maila na logowanie', async () => {
    mockBackend(); window.history.replaceState({}, '', '/verify'); render(<App />);
    await screen.findByLabelText('Twój adres e-mail');
    expect(window.location.pathname).toBe('/login');
  });
  it('obsługuje drag & drop i nie niszczy wcześniejszego wyboru po błędzie', async () => {
    mockBackend(true); render(<App />);
    const input = await screen.findByLabelText('Wybierz pliki');
    const dropzone = input.closest('.dropzone')!;
    fireEvent.drop(dropzone, { dataTransfer: { files: [new File(['a'], 'a.png')], types: ['Files'] } });
    expect(await screen.findByText('a.png')).toBeInTheDocument();
    fireEvent.drop(dropzone, { dataTransfer: { files: [new File(['b'], 'b.mp4')], types: ['Files'] } });
    expect(await screen.findByRole('alert')).toHaveTextContent('wspólnego formatu');
    expect(screen.getByText('a.png')).toBeInTheDocument();
    expect(screen.queryByText('b.mp4')).not.toBeInTheDocument();
  });
  it('kończy sesję i czyści listę po sygnale z API', async () => {
    mockBackend(true); render(<App />);
    const input = await screen.findByLabelText('Wybierz pliki');
    fireEvent.change(input, { target: { files: [new File(['a'], 'a.png')] } });
    expect(await screen.findByText('a.png')).toBeInTheDocument();
    act(() => { window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT)); });
    expect(await screen.findByLabelText('Twój adres e-mail')).toBeInTheDocument();
    expect(screen.getByText('Sesja wygasła. Zaloguj się ponownie.')).toBeInTheDocument();
    expect(screen.queryByText('a.png')).not.toBeInTheDocument();
  });
  it('pokazuje ponowienie po błędzie połączenia zamiast fałszywego zalogowania', async () => {
    const fetchMock = vi.fn().mockRejectedValueOnce(new TypeError('offline')).mockResolvedValue(json(anonymous, 401));
    vi.stubGlobal('fetch', fetchMock); const user = userEvent.setup(); render(<App />);
    expect(await screen.findByRole('heading', { name: 'Nie mogę się połączyć' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Spróbuj ponownie' }));
    await waitFor(() => expect(screen.getByLabelText('Twój adres e-mail')).toBeInTheDocument());
  });
});
