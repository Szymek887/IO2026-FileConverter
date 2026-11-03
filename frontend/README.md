# Konwuś – Frontend

React 19 + TypeScript + Vite. Wygląd zgodny z projektem z [`docs/frontend-design`](../docs/frontend-design) (pliki `*new.png`), komunikacja wg [`docs/api-contract.md`](../docs/api-contract.md).

## Szybki start

```bash
cd frontend
npm install
npm run dev:mock     # http://localhost:5173 – aplikacja z wbudowanym mockiem API (bez backendu)
```

W trybie mock kod logowania to zawsze **`123456`** (wypisywany też w konsoli przeglądarki).

## Praca z prawdziwym backendem

```bash
# terminal 1
cd backend && uv run uvicorn app.main:app --reload    # :8000
# terminal 2
cd frontend && npm run dev                              # :5173, /api -> :8000 (proxy Vite)
```

- Proxy z `vite.config.ts` przekazuje `/api` do `http://localhost:8000` (inny adres: zmienna `API_PROXY_TARGET`). Frontend i API są na tym samym originie, więc ciasteczko `session` działa bez CORS.
- Do pracy po `http://` ustaw w `backend/.env` `COOKIE_SECURE=false` (Safari odrzuca ciasteczka `Secure` na localhost).
- Z `EMAIL_BACKEND=console` (domyślnie w dev) kod logowania nie jest wysyłany e-mailem, tylko wypisywany w logu backendu: `Login code for <e-mail>: 123456`.

## Skrypty

| Komenda | Opis |
|---|---|
| `npm run dev` | serwer deweloperski z proxy do backendu |
| `npm run dev:mock` | serwer deweloperski z mockiem API (MSW) |
| `npm run build` | sprawdzenie typów + build produkcyjny do `dist/` |
| `npm run lint` | oxlint |
| `npm test` | testy jednostkowe i komponentów (Vitest + Testing Library) |
| `npm run test:e2e` | testy E2E w Chromium (Playwright; desktop 1280×800 i Pixel 7) |

Przed pierwszym `test:e2e`: `npx playwright install chromium`. Testy E2E same uruchamiają `dev:mock` na porcie 5174. Aby przetestować działającą instancję (np. z prawdziwym backendem): `E2E_BASE_URL=http://localhost:5173 npm run test:e2e`.

## Struktura

```
src/
  api/          client.ts (fetch + XHR z postępem uploadu, ApiError), types.ts (typy z kontraktu)
  components/   Mascot (ludzik: twarz, ręce, dymek, animacje), Header, Icons (logo, ikony, konfetti)
  screens/      LoginScreen (krok 1–2), ConverterScreen -> HomeStage / PickStage / ResultStage
  lib/          files.ts (walidacja plików wg /formats), format.ts (rozmiary, maskowanie e-maila),
                useConversion.ts (wysyłka + polling zadań)
  mocks/        handlers.ts – mock API wg kontraktu (dev:mock, Vitest, Playwright)
e2e/            testy Playwright
```

## Decyzje projektowe

- **Inny format dla każdego pliku** (jak na ekranie 4): każdy plik wysyłany jest jako osobne zadanie `POST /api/jobs` z własnym `target_format`. Backend bez zmian.
- **Lista formatów** pochodzi zawsze z `GET /api/formats`, więc oferowane są tylko konwersje obsługiwane przez backend (np. MP4 → MP3 z makiety nie jest dostępne – backend konwertuje w obrębie kategorii).
- **„Pobierz wszystko (.zip)”** – ZIP budowany w przeglądarce (JSZip), backend nie ma takiego endpointu.
- **Pobieranie** przez `fetch` → Blob, żeby pokazać polski komunikat przy `410 FILE_EXPIRED` zamiast zapisywać plik z JSON-em błędu.
- **Walidacja po stronie klienta** (format, rozmiar ≤ 250 MB, ≤ 2 pliki) z komunikatami takimi jak w backendzie; ostateczne sprawdzenie robi backend.
- **Animacje** w czystym CSS (mruganie, oczy śledzące kursor, machanie, dymki, konfetti, pasek postępu); wyłączane przy `prefers-reduced-motion`. Elementy klikalne nie są animowane w sposób ciągły.

## Mock API – przypadki testowe

| Nazwa pliku zawiera | Efekt |
|---|---|
| `uszkodzony` | upload odrzucony: `422 CORRUPTED_FILE` |
| `blad` | zadanie kończy się `result.status = "error"` |
