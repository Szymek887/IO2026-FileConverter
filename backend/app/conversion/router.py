import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser, get_current_user
from app.conversion import formats, jobs, storage
from app.conversion.schemas import CategoryInfo, FormatsResponse, JobListResponse, JobResponse
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


@router.get("/jobs", response_model=JobListResponse)
def list_jobs(user: CurrentUser, db: Annotated[Session, Depends(get_db)]) -> JobListResponse:
    """The current user's jobs from the last 24 h, newest first (lets the frontend restore
    the list after a page reload)."""
    return JobListResponse(
        items=[jobs.job_response(job) for job in jobs.recent_jobs(db, user.email)]
    )


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str, user: CurrentUser, db: Annotated[Session, Depends(get_db)]) -> JobResponse:
    """Job status and result. The frontend polls this every 1–2 s until `done`/`error`.

    Errors: FORBIDDEN (403, another user's job), NOT_FOUND (404).
    """
    return jobs.job_response(jobs.get_owned_job(db, job_id, user.email))


@router.get("/jobs/{job_id}/files/{index}", response_class=FileResponse)
def download_file(
    job_id: str, index: str, user: CurrentUser, db: Annotated[Session, Depends(get_db)]
) -> FileResponse:
    """Download output file `index` (0-based, order of `result.output_files`).

    `index` is a `str`, so a bad one gives 404 and not a validation error. Errors: FORBIDDEN
    (403), NOT_FOUND (404: bad id/index or job not `done`), FILE_EXPIRED (410).
    """
    job = jobs.get_owned_job(db, job_id, user.email)
    output, path = jobs.get_download(job, index)
    return FileResponse(
        path,
        media_type=formats.MIME_TYPES[job.target_format],
        headers={"Content-Disposition": storage.content_disposition(output.name)},
    )
