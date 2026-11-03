# Integracja osoby B

Osoba A dostarcza uruchomiony frontend, logowanie, sprawdzenie sesji, konfigurację formatów, import oraz walidację wyboru. Konwersja nie jest zaimplementowana.

## Miejsce pracy

Rozwijaj `src/features/conversion/ConversionPanel.tsx`. Możesz dodać obok własne komponenty i hooki. `HomePage` już renderuje ten panel i przekazuje:

| Prop | Typ | Znaczenie |
| --- | --- | --- |
| `files` | `readonly File[]` | Wybrane i wstępnie zwalidowane pliki. Oryginalne obiekty do `FormData`. |
| `formats` | `FormatsConfig` | Odpowiedź `/api/formats`, wspólna dla walidacji i pickera. |
| `onReset()` | `() => void` | Czyści wybór po zakończeniu, gdy użytkownik chce konwertować kolejne pliki. |
| `onBusyChange(busy)` | `(boolean) => void` | Blokuje import i usuwanie plików na czas operacji. |

Na początek panel wyświetla tylko potwierdzenie dodania plików. Zastąp jego zawartość właściwą obsługą konwersji. Nie zmieniaj logowania ani wspólnego klienta bez uzgodnienia.

## Format docelowy

Użyj `getCommonTargets(files, formats)` z `src/utils/files.ts`. To przecięcie dozwolonych celów, już z aliasami rozszerzeń. Dla WAV + MP3 wynikiem jest `['flac']`. Nie wyświetlaj samego formatu źródłowego jako celu. Zresetuj wybrany format i stare wyniki po zmianie listy plików. Sprawdzaj, czy zapisany wybór nadal występuje w aktualnej liście.

Aktualny kontrakt ma **jedno** `target_format` na zlecenie. Obsługa różnych celów dla dwóch plików lub konwersji MP4 do MP3 wymaga nowej wersji kontraktu.

## Zlecenie i postęp

1. Przy kliknięciu „Konwertuj” ustaw `onBusyChange(true)`.
2. Zbuduj `FormData`, powtórz pole `files` dla każdego pliku, dodaj `target_format`.
3. Wyślij `POST /api/jobs`. Dla postępu uploadu użyj `XMLHttpRequest` z `xhr.withCredentials = true` albo axios; standardowy fetch nie raportuje postępu wysyłania. Adres bazowy eksportuje `src/config.ts` jako `apiBaseUrl`.
4. **Nie ustawiaj ręcznie Content-Type dla FormData.** Przeglądarka musi dopisać boundary.
5. Po odpowiedzi `202` odpytuj `GET /api/jobs/{id}` co 1–2 s. Zatrzymaj polling na `done` i `error`. Zadbaj o brak równoległych żądań i usunięcie timerów/anulowanie żądań po odmontowaniu panelu lub wylogowaniu.
6. Przy końcu, błędzie i anulowaniu odblokuj wybór przez `onBusyChange(false)`.

Do JSON i pollingu możesz używać `apiRequest<T>()`. Klient ma domyślny timeout 20 s; dla długiego uploadu ustaw odpowiedni `timeoutMs` (wartość `0` wyłącza timeout). W przypadku XHR obsłuż jego timeout osobno. XHR powinien również zareagować na `401 UNAUTHENTICATED`, emitując `SESSION_EXPIRED_EVENT` z `src/api/client.ts`.

## Wynik i błędy

`result` jest `null`, dopóki zadanie jest `queued` lub `processing`. Błąd konwersji jest w obiekcie zadania (`status: 'error'`), nawet przy HTTP 200. Nie próbuj odczytać `output_files` przed końcem.

Po sukcesie pokaż `result.message` i linki `result.output_files[].url`. Są względnymi adresami z API. Użytkownik ma aktywną sesję cookie, więc zwykły link tej samej domeny wystarczy. Po wygaśnięciu wyniku endpoint zwraca `410 FILE_EXPIRED`. Całe zlecenie jest atomowe: awaria jednego pliku oznacza brak wyników obu.

Kontrakt nie udostępnia endpointu ZIP ani gotowego archiwum. Nie dodawaj pozornego przycisku „Pobierz ZIP”. Możecie uzgodnić rozszerzenie backendu lub osobno zaimplementować archiwizowanie wyników. Historia `GET /api/jobs` jest opcjonalna i może być niedostępna.

Logika reaguje na `ApiError.code`, a użytkownik widzi `ApiError.message`. Samo `401` nie wystarcza do globalnego przekierowania, bo `INVALID_OTP` i `OTP_EXPIRED` również mają ten status.

## Uruchomienie wspólnej pracy

`npm run dev:demo` pozwala obejrzeć i sprawdzić część A. Mock nie implementuje `/jobs` i nie symuluje sukcesu konwersji. Do implementacji i testów części B użyjcie backendu albo rozszerzcie mock zgodnie z kontraktem.

Po zmianach uruchom `npm run check`. Przekaż osobie od backendu wyniki wspólnych testów z `docs/TESTY.md`.
