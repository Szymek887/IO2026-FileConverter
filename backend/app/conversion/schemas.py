"""Response models of the conversion endpoints (shapes from `docs/api-contract.md`)."""

from pydantic import BaseModel

from app.conversion.formats import Category, Format


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
