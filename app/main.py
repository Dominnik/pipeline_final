import logging
from uuid import uuid4

from fastapi import FastAPI
from fastapi import Request
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.core.config import get_settings
from app.core.logging import configure_logging, reset_request_id, set_request_id
from app.exceptions import ServiceUnavailableError


settings = get_settings()
configure_logging(settings)
logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Production-like FastAPI service skeleton for LLM text summarization.",
)

app.include_router(router)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = str(uuid4())
    request.state.request_id = request_id
    token = set_request_id(request_id)

    try:
        response = await call_next(request)
    except Exception as exc:
        logger.error(
            "Request failed",
            extra={
                "event": "request_failed",
                "error_type": exc.__class__.__name__,
            },
        )
        response = JSONResponse(
            status_code=500,
            content={
                "detail": "Внутренняя ошибка сервиса.",
                "request_id": request_id,
            },
        )

    response.headers["X-Request-ID"] = request_id
    logger.info(
        "Request completed",
        extra={
            "event": "request_completed",
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
        },
    )
    reset_request_id(token)

    return response


@app.exception_handler(ServiceUnavailableError)
async def service_unavailable_handler(
    request: Request,
    exc: ServiceUnavailableError,
) -> JSONResponse:
    request_id = request.state.request_id
    logger.error(
        "Request failed",
        extra={
            "event": "request_failed",
            "error_type": exc.__class__.__name__,
            "request_id": request_id,
        },
    )
    return JSONResponse(
        status_code=503,
        content={
            "detail": "Сервис суммаризации временно недоступен.",
            "request_id": request_id,
        },
    )


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = request.state.request_id
    logger.error(
        "Request failed",
        extra={
            "event": "request_failed",
            "error_type": exc.__class__.__name__,
            "request_id": request_id,
        },
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Внутренняя ошибка сервиса.",
            "request_id": request_id,
        },
    )
