import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser, get_current_user
from app.conversion import formats, jobs, storage
from app.conversion.schemas import CategoryInfo, FormatsResponse, JobResponse
from app.conversion.upload import FILES_FIELD, TARGET_FIELD, receive_upload
from app.conversion.validation import validate_upload
from app.core.config import settings
from app.core.db import get_db

router = APIRouter(prefix="/api", tags=["conversion"])


@router.get(
    "/formats",
    response_model=FormatsResponse,
    dependencies=[Depends(get_current_user)],
)
def get_formats() -> FormatsResponse:
    """Supported formats, limits and allowed conversions (source of truth for the frontend)."""
    return FormatsResponse(
        max_file_size=settings.max_file_size,
        max_files_per_job=settings.max_files_per_job,
        categories=[
            CategoryInfo(id=category, label=formats.CATEGORY_LABELS[category], formats=list(fmts))
            for category, fmts in formats.CATEGORY_FORMATS.items()
        ],
        conversions={fmt: formats.allowed_targets(fmt) for fmt in formats.Format},
        extension_aliases=formats.EXTENSION_ALIASES,
    )


# The body is parsed by `receive_upload` (streaming), so FastAPI can't infer this schema.
_UPLOAD_REQUEST_BODY = {
    "required": True,
    "content": {
        "multipart/form-data": {
            "schema": {
                "type": "object",
                "required": [FILES_FIELD, TARGET_FIELD],
                "properties": {
                    FILES_FIELD: {
                        "type": "array",
                        "items": {"type": "string", "format": "binary"},
                        "minItems": 1,
                        "maxItems": 2,
                        "description": "Repeat the field for each file. Max 250 MB per file.",
                    },
                    TARGET_FIELD: {"type": "string", "enum": [f.value for f in formats.Format]},
                },
            },
            "encoding": {FILES_FIELD: {"style": "form", "explode": True}},
        }
    },
}


@router.post(
    "/jobs",
    status_code=202,
    response_model=JobResponse,
    openapi_extra={"requestBody": _UPLOAD_REQUEST_BODY},
)
async def post_job(
    request: Request, user: CurrentUser, db: Annotated[Session, Depends(get_db)]
) -> JobResponse:
    """Upload 1–2 files and queue their conversion to `target_format`.

    Authentication is checked before the body is read. Errors: NO_FILES, TOO_MANY_FILES,
    VALIDATION_ERROR, INVALID_TARGET (400), FILE_TOO_LARGE (413), UNSUPPORTED_FORMAT (415),
    CORRUPTED_FILE (422).
    """
    job_id = str(uuid.uuid4())
    try:
        upload = await receive_upload(request, job_id)
        target = await validate_upload(upload)
        job = jobs.create_job(db, job_id, user.email, upload, target)
    except BaseException:
        storage.remove_uploads(job_id)
        raise
    request.app.state.job_runner.submit(job.id)
    return jobs.job_response(job)
