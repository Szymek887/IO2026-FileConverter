from fastapi import APIRouter, Depends

from app.auth.deps import get_current_user
from app.conversion import formats
from app.conversion.schemas import CategoryInfo, FormatsResponse
from app.core.config import settings

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
