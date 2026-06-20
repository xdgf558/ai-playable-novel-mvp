from fastapi import APIRouter

from app.schemas.templates import TemplatesResponse
from app.services.template_service import list_templates

router = APIRouter(tags=["templates"])


@router.get("/templates", response_model=TemplatesResponse)
async def get_templates(locale: str = "zh-Hans") -> TemplatesResponse:
    return TemplatesResponse(templates=list_templates(locale=locale))
