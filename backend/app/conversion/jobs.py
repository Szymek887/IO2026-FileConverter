"""Job service: create a job from a validated upload, load jobs for their owner and
serialize jobs for the API."""

import uuid

from sqlalchemy.orm import Session

from app.conversion import storage
from app.conversion.formats import CATEGORY_OF, Format
from app.conversion.models import InputFile, Job
from app.conversion.schemas import InputFileInfo, JobResponse, OutputFileInfo, ResultInfo
from app.conversion.upload import UploadResult
from app.core.errors import ErrorCode, error
from app.core.messages import NOT_FOUND_JOB


def create_job(
    db: Session, job_id: str, user_email: str, upload: UploadResult, target: Format
) -> Job:
    """Insert a queued job with its input files (already on disk) and commit."""
    job = Job(id=job_id, user_email=user_email, target_format=target)
    job.files = [
        InputFile(
            id=staged.id,
            position=position,
            name=staged.name,
            extension=staged.format,
            category=CATEGORY_OF[staged.format],
            size=staged.size,
            path=storage.to_relative(staged.path),
        )
        for position, staged in enumerate(upload.files)
    ]
    db.add(job)
    db.commit()
    return job


def get_owned_job(db: Session, job_id: str, user_email: str) -> Job:
    """The job if it belongs to the user. `404 NOT_FOUND` for unknown or malformed IDs,
    `403 FORBIDDEN` for another user's job (as in the contract)."""
    try:
        canonical_id = str(uuid.UUID(job_id))
    except ValueError:
        raise error(ErrorCode.NOT_FOUND, message=NOT_FOUND_JOB) from None
    job = db.get(Job, canonical_id)
    if job is None:
        raise error(ErrorCode.NOT_FOUND, message=NOT_FOUND_JOB)
    if job.user_email != user_email:
        raise error(ErrorCode.FORBIDDEN)
    return job


def download_url(job_id: str, index: int) -> str:
    return f"/api/jobs/{job_id}/files/{index}"


def job_response(job: Job) -> JobResponse:
    """The contract's Job object (`docs/api-contract.md` §5)."""
    result = None
    if job.result is not None:
        result = ResultInfo(
            finished_at=job.result.finished_at,
            status=job.result.status,
            message=job.result.message,
            output_files=[
                OutputFileInfo(
                    index=out.index,
                    name=out.name,
                    size=out.size,
                    url=download_url(job.id, out.index),
                )
                for out in job.result.outputs
            ],
            expires_at=job.result.expires_at,
        )
    return JobResponse(
        id=job.id,
        created_at=job.created_at,
        target_format=job.target_format,
        status=job.status,
        files=[
            InputFileInfo(
                id=f.id, name=f.name, extension=f.extension, category=f.category, size=f.size
            )
            for f in job.files
        ],
        result=result,
    )
