# KONWUŚ — frontend, osoba A

Gotowy projekt React + TypeScript + Vite do umieszczenia w repozytorium. Implementuje zakres osoby A: logowanie e-mailem i OTP, sesję, routing, ekran główny, import i walidację plików. Wygląd nawiązuje do dostarczonych makiet (kremowe tło, pomarańczowe akcenty, brązowa maskotka).

**Konwersja jest zakresem osoby B.** Ten projekt nie wykonuje pozorowanej konwersji. Miejsce na wybór formatu, wysłanie zlecenia, polling i pobieranie jest przygotowane w `src/features/conversion/ConversionPanel.tsx`.

## 1. Uruchomienie bez backendu

Wymagane: Node.js **22.12 lub nowszy** oraz npm. Polecenia działają również w terminalu VS Code / PowerShell.

Po rozpakowaniu archiwum wejdź do katalogu `konwus-frontend`:

```sh
npm ci
npm run dev:demo
```

Otwórz **http://localhost:5173**. Podaj dowolny poprawny e-mail, a na kolejnym ekranie kod **123456**. Nie jest wysyłany prawdziwy e-mail. Możesz sprawdzić błędny kod, ponowne wysłanie, sesję, wybór plików i wylogowanie.

Demo działa tylko na serwerze developerskim uruchomionym w tym trybie. Standardowe `npm run dev` i produkcyjne `npm run build` korzystają z rzeczywistego API. Kod mocka nie trafia do builda produkcyjnego. Stan demo jest osobny od rzeczywistego logowania.

## 2. Uruchomienie z Waszym backendem

1. Uruchom backend na **http://localhost:8000**.
2. W tym katalogu wykonaj:

```sh
npm ci
npm run dev
```

3. Otwórz **http://localhost:5173** i użyj kodu z prawdziwego e-maila.

Vite przekazuje `/api` do backendu. Przeglądarka wysyła żądania do swojego originu, a klient API zawsze ustawia `credentials: "include"`.

Nie musisz tworzyć `.env`, jeśli korzystasz z domyślnych adresów. Jeśli backend ma inny adres, skopiuj `.env.example` do `.env` i zmień `API_PROXY_TARGET`. Po zmianie uruchom Vite ponownie. `VITE_API_BASE_URL` pozostaw `/api` przy korzystaniu z proxy. Zmienne `VITE_*` są widoczne w przeglądarce — nie wpisuj tam sekretów.

Jeśli backend jest wyłączony, zwykły tryb pokaże błąd połączenia. To nie jest tryb demo. Użyj wtedy `npm run dev:demo` albo uruchom backend.

## 3. Co jest zrobione

| Część | Zachowanie |
| --- | --- |
| Klient API | JSON, FormData, polskie komunikaty błędów, timeout, anulowanie i obsługa pustego `204` |
| Logowanie | `POST /api/auth/request-otp`, walidacja e-maila i stan wysyłania |
| OTP | `POST /api/auth/verify-otp`, 6 cyfr, wklejanie, zera na początku, błędny/wygasły kod i limit prób |
| Ponowne wysłanie | Odliczanie z `resend_available_in`, korekta z `details.retry_after_seconds` |
| Odświeżenie OTP | E-mail i terminy są odtwarzane po odświeżeniu tej samej karty |
| Sesja | `GET /api/auth/me` przy starcie, chroniony ekran główny, obsługa wygaśnięcia |
| Wylogowanie | `POST /api/auth/logout`, powrót do logowania i usunięcie wybranych plików z pamięci |
| Formaty i limity | Pobierane z `GET /api/formats`, z ponowieniem po błędzie |
| Import | Wybór z dysku i drag & drop, licznik i usuwanie plików |
| Walidacja | Maks. 2 pliki, maks. 262 144 000 B na plik, obsługiwane rozszerzenia i wspólny cel |
| Aliasowanie | `.JPEG` → `jpg`, `.HEIF` → `heic`; wielkość liter bez znaczenia |
| Routing | `/login`, `/verify`, `/` i ekran 404 |
| UI | Układ na telefon i komputer, widoczny focus, etykiety pól, komunikaty błędów |

Sesja jest obsługiwana przez ciasteczko backendu. Frontend **nie zapisuje tokena, identyfikatora sesji ani wpisanego OTP w localStorage/sessionStorage**. `sessionStorage` przechowuje wyłącznie e-mail i terminy trwającego logowania; osobne dane przykładowe są używane tylko w demo. Same obiekty `File` pozostają w pamięci i po odświeżeniu wymagają ponownego wyboru.

## 4. Umieszczenie w Git

Archiwum zawiera źródła, `package.json`, `package-lock.json`, `.gitignore`, `.env.example`, konfigurację i dokumentację. Nie zawiera `node_modules`, `dist`, `.git`, prawdziwego `.env` ani haseł.

### Gdy macie wspólne repo z backendem

Skopiuj **zawartość** katalogu `konwus-frontend` do katalogu `frontend` w Waszym repo. Pamiętaj o plikach rozpoczynających się kropką. Nie nadpisuj istniejącego frontendu bez porównania zmian.

W głównym katalogu Waszego repo:

```sh
git switch -c feature/frontend-osoba-a
git add frontend
git commit -m "Dodaj frontend KONWUS: logowanie OTP i import plikow"
git push -u origin feature/frontend-osoba-a
```

Uruchamianie po skopiowaniu:

```sh
cd frontend
npm ci
npm run dev:demo
```

### Gdy zakładacie osobne repo frontendu

W katalogu `konwus-frontend`:

```sh
git init -b main
git add .
git commit -m "Dodaj frontend KONWUS osoby A"
```

Następnie dodajcie URL Waszego repo jako `origin` i wykonajcie push. W tej paczce nie jest skonfigurowany żaden zdalny adres.

## 5. Kontrola i build

```sh
npm run check
```

Uruchamia kontrolę TypeScript, testy i build. Dodatkowo możesz użyć osobno `npm test`, `npm run typecheck` lub `npm run build`.

Build trafia do `dist`. `npm run preview` służy do lokalnego obejrzenia builda, ale **nie zastępuje produkcyjnego proxy do API**. Żeby w tym trybie testować rzeczywiste logowanie, API musi być dostępne pod wybranym adresem. Najprościej podczas pracy korzystać z `npm run dev`.

Na produkcji serwuj `dist`, przekazuj `/api/*` do Waszego backendu i ustaw fallback SPA: nieznane ścieżki frontendu, np. `/verify`, muszą zwracać `index.html`. HTTPS i ustawienie ciasteczka sesji (`HttpOnly`, `Secure`, `SameSite`) są zadaniem backendu/serwera. Nie zastępuj ciasteczka tokenem w localStorage.

## 6. Ważne różnice: makiety a API

Implementacja stosuje dostarczony `docs/api-contract.md` v1.0:

- Zlecenie ma **jeden wspólny format docelowy** dla maksymalnie dwóch plików.
- Dostępne cele to **przecięcie** list `conversions` obu plików. Np. WAV + MP3 można wspólnie przekonwertować do FLAC.
- MP4 + PNG nie mają wspólnego celu i są odrzucane jako wspólny wybór.
- MP4 → MP3 i AVI z części makiet nie występują w dostarczonym API. Nie są dopisywane na sztywno.
- Limit opisany jako 250 MB w kontrakcie oznacza dokładnie **250 MiB = 262 144 000 B**. Równa wielkość jest akceptowana.
- Frontend sprawdza nazwę, wielkość i zgodność wyboru. Weryfikacja zawartości pliku, jego uszkodzenia i ostateczne limity zawsze należą do backendu.

Jeśli chcecie inne zachowanie, najpierw uzgodnijcie zmianę kontraktu z osobą od backendu.

## 7. Gdzie co znaleźć

| Ścieżka | Odpowiedzialność |
| --- | --- |
| `src/api/client.ts` | Wspólny klient API i klasa `ApiError` |
| `src/api/auth.ts` | Cztery endpointy logowania/sesji |
| `src/api/formats.ts` | Pobieranie i kontrola konfiguracji formatów |
| `src/auth/AuthProvider.tsx` | Stan sesji, logowanie i wylogowanie |
| `src/auth/challenge.ts` | Odtwarzanie trwającego logowania OTP |
| `src/hooks/useAuth.ts` | Dostęp do sesji w komponentach |
| `src/hooks/useSelectedFiles.ts` | Dodawanie, usuwanie i atomowa walidacja wyboru |
| `src/utils/files.ts` | Aliasowanie, rozmiary, akceptowane rozszerzenia i wspólne cele |
| `src/pages/*` | Ekrany logowania, OTP i konwertera |
| `src/components/*` | Nagłówek, maskotka, dropzone, lista plików, komunikaty |
| `src/features/conversion/ConversionPanel.tsx` | Punkt integracji osoby B |
| `src/demo/*` | Osobny mock developerski |
| `docs/INTEGRACJA_OSOBA_B.md` | Instrukcja dla kolegi |
| `docs/TESTY.md` | Weryfikacja i scenariusze z backendem |

Sprawdzono build i zachowanie z testowym API. Prawdziwy backend, wysyłka e-maili i ustawienie ciasteczek wymagają jeszcze wspólnego testu z Waszym serwerem.

Dokumentacja narzędzi: [Vite — uruchomienie](https://vite.dev/guide/), [Vite — proxy](https://vite.dev/config/server-options#server-proxy), [React](https://react.dev/learn).
