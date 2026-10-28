import string

import pytest

from app.conversion.formats import Category
from app.core import messages
from app.core.errors import ErrorCode, error


def placeholders(template: str) -> set[str]:
    return {field for _, field, _, _ in string.Formatter().parse(template) if field}


def test_corrupted_file_variant_for_every_category():
    assert set(messages.CORRUPTED_FILE_BY_CATEGORY) == {c.value for c in Category}


@pytest.mark.parametrize(
    "template",
    [
        *messages.CORRUPTED_FILE_BY_CATEGORY.values(),
        messages.CONVERSION_FAILED,
        messages.CONVERSION_TIMEOUT,
    ],
)
def test_file_messages_take_only_the_file_name(template):
    assert placeholders(template) == {"file"}
    assert "„film.mov”" in template.format(file="film.mov")


@pytest.mark.parametrize(
    "template",
    [
        messages.CONVERSION_SUCCESS,
        messages.JOB_INTERRUPTED,
        messages.NOT_FOUND_FILE,
    ],
)
def test_fixed_messages_have_no_placeholders(template):
    assert placeholders(template) == set()


def test_corrupted_image_error_matches_contract_example():
    exc = error(
        ErrorCode.CORRUPTED_FILE,
        message=messages.CORRUPTED_FILE_BY_CATEGORY["image"],
        file="zdjecie.png",
    )
    assert exc.http_status == 422
    assert exc.message == "Plik „zdjecie.png” jest uszkodzony lub nie jest prawidłowym obrazem."
    assert exc.details == {"file": "zdjecie.png"}


def test_invalid_target_matches_contract_example():
    exc = error(ErrorCode.INVALID_TARGET, file="nagranie.wav", target="PNG")
    assert exc.message == "Nie można przekonwertować pliku „nagranie.wav” do formatu PNG."
