"""Response models of the conversion endpoints (shapes from `docs/api-contract.md`)."""

from pydantic import BaseModel

from app.conversion.formats import Category, Format
from app.conversion.models import JobStatus, ResultStatus


class CategoryInfo(BaseModel):
    id: Category
    label: str
    formats: list[Format]


class FormatsResponse(BaseModel):
    max_file_size: int
    max_files_per_job: int
    categories: list[CategoryInfo]
    conversions: dict[Format, list[Format]]
    extension_aliases: dict[str, Format]


class InputFileInfo(BaseModel):
    id: str
    name: str
    extension: Format
    category: Category
    size: int


class OutputFileInfo(BaseModel):
    index: int
    name: str
    size: int
    url: str  # relative download URL


class ResultInfo(BaseModel):
    finished_at: int
    status: ResultStatus
    message: str  # Polish
    output_files: list[OutputFileInfo]  # empty on error
    expires_at: int | None  # None on error


class JobResponse(BaseModel):
    id: str
    created_at: int
    target_format: Format
    status: JobStatus
    files: list[InputFileInfo]
    result: ResultInfo | None  # None while queued/processing
