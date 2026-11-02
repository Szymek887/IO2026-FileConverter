"""Checks on a fully received upload (rules 5–8 of the plan; 1–4 run while streaming).

5. no file                                        -> 400 NO_FILES
6. `target_format` missing                        -> 400 VALIDATION_ERROR
7. target unknown / same as source / other category, per file -> 400 INVALID_TARGET
8. content doesn't match the extension, per file  -> 422 CORRUPTED_FILE

All files pass rule 7 before any is probed: probing (ffprobe, full image decode) is the
expensive part.
"""

from starlette.concurrency import run_in_threadpool

from app.conversion.formats import CATEGORY_OF, Format, can_convert, parse_format
from app.conversion.probe import ProbeError, probe
from app.conversion.upload import StagedFile, UploadResult
from app.core.errors import ErrorCode, error
from app.core.messages import CORRUPTED_FILE_BY_CATEGORY


async def validate_upload(upload: UploadResult) -> Format:
    """Return the target format, or raise the first `AppError` in rule order."""
    if not upload.files:
        raise error(ErrorCode.NO_FILES)
    if not upload.target_format:
        raise error(ErrorCode.VALIDATION_ERROR, fields={"target_format": "Field required"})

    target = parse_format(upload.target_format)
    for staged in upload.files:
        if target is None or not can_convert(staged.format, target):
            shown = target or upload.target_format
            raise error(
                ErrorCode.INVALID_TARGET,
                file=staged.name,
                format_args={"target": str(shown).upper()},
            )
    assert target is not None

    for staged in upload.files:
        await _check_content(staged)
    return target


async def _check_content(staged: StagedFile) -> None:
    try:
        await run_in_threadpool(probe, staged.path, staged.format)
    except ProbeError as exc:
        category = CATEGORY_OF[staged.format]
        raise error(
            ErrorCode.CORRUPTED_FILE,
            message=CORRUPTED_FILE_BY_CATEGORY[category],
            file=staged.name,
        ) from exc
