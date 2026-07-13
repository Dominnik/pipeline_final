from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.schemas import HealthResponse, HealthStatus


router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    llm_configured = settings.llm_configured
    status = HealthStatus.ok if llm_configured else HealthStatus.degraded

    return HealthResponse(
        status=status,
        app_env=settings.app_env,
        llm_configured=llm_configured,
    )
