from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from app.api.errors import AppError, app_error_handler, validation_exception_handler
from app.api.router import api_router
from app.api.routes.health import router as health_router
from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
    )
    application.add_exception_handler(
        RequestValidationError,
        validation_exception_handler,
    )
    application.add_exception_handler(AppError, app_error_handler)
    application.include_router(health_router)
    application.include_router(api_router)
    application.include_router(health_router, prefix="/storycat")
    application.include_router(api_router, prefix="/storycat")
    return application


app = create_app()
