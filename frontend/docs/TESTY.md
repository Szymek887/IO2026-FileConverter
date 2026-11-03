# Weryfikacja

## Wykonane kontrole

- Kontrola TypeScript: `npm run typecheck`.
- Testy automatyczne: `npm test` — klient API, walidacja plików, logowanie i ekrany.
- Build produkcyjny: `npm run build`.
- Kontrola, że build produkcyjny nie zawiera transportu demo i przykładowego kodu logowania.
- Kontrola wizualna w przeglądarce na lokalnym podglądzie.

Testy korzystają z kontrolowanych odpowiedzi API. Nie potwierdzają dostarczania e-maili, działania prawdziwego cookie ani konwersji na backendzie.

## Scenariusze do wspólnego sprawdzenia z backendem

| Działanie | Oczekiwany wynik |
| --- | --- |
| Start bez sesji | `/auth/me` → 401, ekran logowania |
| Poprawny e-mail | 202, przejście na ekran kodu |
| Błędny e-mail | Komunikat, bez przejścia do konwertera |
| Zły kod | 401 INVALID_OTP, pozostanie na ekranie kodu |
| Kod zaczynający się od 0 | Wysyłane jest pełne 6 znaków, bez konwersji do liczby |
| Wygasły/zużyty kod | Komunikat, potrzeba pobrania nowego kodu |
| Pięć błędnych prób | TOO_MANY_ATTEMPTS, weryfikacja zablokowana do pobrania nowego kodu |
| Ponowne wysłanie przed 60 s | Przycisk z odliczaniem; API może zwrócić 429 z terminem |
| Odświeżenie ekranu OTP | E-mail i dotychczasowe terminy pozostają w tej samej karcie |
| Limit 10 zalogowanych | 503 USER_LIMIT_REACHED, komunikat z backendu |
| Poprawny kod | Cookie z backendu i ekran importu |
| Odświeżenie po zalogowaniu | GET /auth/me odtwarza sesję, bez ponownego OTP |
| Wygaśnięcie sesji | Powrót do logowania; lista plików znika |
| Wylogowanie | 204 bez treści; cookie unieważnione przez backend |
| Backend niedostępny | Komunikat i przycisk ponowienia, bez udawania zalogowania |
| Błąd GET /formats | Import zablokowany do poprawnego pobrania konfiguracji |
| Jeden obsługiwany plik | Lista, licznik i możliwość usunięcia |
| Drag & drop | Taki sam wynik walidacji jak przy wyborze z dysku |
| Dwa zgodne pliki | Zostają na liście |
| Trzeci plik | Błąd, poprzednia lista pozostaje |
| Plik 262 144 000 B | Akceptowany |
| Plik 262 144 001 B | Odrzucony |
| Plik PDF lub bez rozszerzenia | Odrzucony |
| Duże litery .JPEG/.HEIF | Alias do JPG/HEIC |
| WAV + MP3 | Akceptowane, wspólny cel FLAC |
| MP4 + PNG | Błąd braku wspólnego formatu docelowego |
| Zmiana rozszerzenia uszkodzonego pliku | Ostateczna kontrola dopiero po stronie backendu przy POST /jobs |
| Telefon i klawiatura | Brak przewijania w poziomie, działające pola, focus i przyciski |

Po podłączeniu części B należy dodać testy uploadu, pollingu, awarii konwersji, pobierania i wygaśnięcia wyników.
