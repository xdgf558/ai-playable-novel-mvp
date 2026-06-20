from fastapi import APIRouter

from app.api.routes.device_session import router as device_session_router
from app.api.routes.feedback import router as feedback_router
from app.api.routes.stories import router as stories_router
from app.api.routes.templates import router as templates_router

api_router = APIRouter(prefix="/v1")
api_router.include_router(device_session_router)
api_router.include_router(templates_router)
api_router.include_router(stories_router)
api_router.include_router(feedback_router)
