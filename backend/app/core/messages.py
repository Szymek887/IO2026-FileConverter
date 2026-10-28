"""All user-facing Polish texts returned by the API, kept in one place.

Templates use `str.format` placeholders; the placeholder names match the keys put into
the error's `details` (e.g. `{file}`, `{retry_after_seconds}`).
"""

ERROR_MESSAGES: dict[str, str] = {
    # General
    "VALIDATION_ERROR": "Nieprawidłowe dane żądania.",
    "NOT_FOUND": "Nie znaleziono zasobu.",
    "INTERNAL_ERROR": "Wystąpił nieoczekiwany błąd serwera.",
    # Authentication
    "INVALID_EMAIL": "Podaj poprawny adres e-mail.",
    "UNAUTHENTICATED": "Sesja wygasła. Zaloguj się ponownie.",
    "INVALID_OTP": "Nieprawidłowy kod logowania.",
    "OTP_EXPIRED": "Kod logowania wygasł. Poproś o nowy kod.",
    "OTP_RATE_LIMITED": "Nowy kod możesz wysłać za {retry_after_seconds} s.",
    "TOO_MANY_ATTEMPTS": "Przekroczono liczbę prób. Poproś o nowy kod.",
    "USER_LIMIT_REACHED": (
        "Osiągnięto limit {limit} jednocześnie zalogowanych użytkowników. Spróbuj ponownie później."
    ),
    # Upload & validation
    "NO_FILES": "Nie wybrano żadnego pliku.",
    "TOO_MANY_FILES": "Możesz przesłać maksymalnie {limit} pliki naraz.",
    "FILE_TOO_LARGE": "Plik „{file}” przekracza maksymalny rozmiar {limit_mb} MB.",
    "UNSUPPORTED_FORMAT": "Format pliku „{file}” nie jest obsługiwany.",
    "CORRUPTED_FILE": "Plik „{file}” jest uszkodzony lub ma nieprawidłową zawartość.",
    "INVALID_TARGET": "Nie można przekonwertować pliku „{file}” do formatu {target}.",
    # Jobs & downloads
    "FORBIDDEN": "Brak dostępu do tego zadania.",
    "FILE_EXPIRED": "Plik wynikowy wygasł. Wykonaj konwersję ponownie.",
}

# Message overrides for specific situations (pass as `error(..., message=...)`)
NOT_FOUND_JOB = "Nie znaleziono zadania."
EMAIL_SEND_FAILED = "Nie udało się wysłać kodu logowania. Spróbuj ponownie później."

# Success / status messages
OTP_SENT = "Wysłaliśmy kod logowania na adres {email}."
