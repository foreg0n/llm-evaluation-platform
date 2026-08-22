from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from opentelemetry.instrumentation.celery import CeleryInstrumentor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from backend.api.auth import router as auth_router
from backend.api.crud import router as crud_router
from backend.api.health import router as health_router
from backend.api.metrics import router as metrics_router
from backend.api.runs import router as runs_router
from backend.config import get_settings
from backend.db.session import dispose_engine
from backend.error_monitoring import configure_error_monitoring
from backend.observability import (
    REQUEST_ID_HEADER,
    RequestContextMiddleware,
    configure_logging,
)
from backend.services.task_manager import task_manager
from backend.tracing import configure_tracing, shutdown_tracing


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    await task_manager.shutdown()
    await dispose_engine()
    if getattr(app.state, "tracing_enabled", False):
        CeleryInstrumentor().uninstrument()
        FastAPIInstrumentor.uninstrument_app(app)
    shutdown_tracing(getattr(app.state, "tracer_provider", None))


async def unhandled_exception_response(
    request: Request,
    _exception: Exception,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    headers = {REQUEST_ID_HEADER: request_id} if request_id else None
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
        headers=headers,
    )


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings)
    error_monitoring_enabled = configure_error_monitoring(
        settings,
        service_name="llm-evaluation-api",
    )
    tracer_provider = configure_tracing(
        settings,
        service_name="llm-evaluation-api",
    )
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
    )
    application.add_exception_handler(Exception, unhandled_exception_response)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    application.add_middleware(RequestContextMiddleware)
    application.include_router(health_router)
    application.include_router(metrics_router)
    application.include_router(auth_router)
    application.include_router(crud_router)
    application.include_router(runs_router)
    application.state.tracer_provider = tracer_provider
    application.state.tracing_enabled = tracer_provider is not None
    application.state.error_monitoring_enabled = error_monitoring_enabled
    if tracer_provider is not None:
        FastAPIInstrumentor.instrument_app(
            application,
            tracer_provider=tracer_provider,
            excluded_urls=r".*/metrics$,.*\/health$,.*\/ready$",
        )
        CeleryInstrumentor().instrument(tracer_provider=tracer_provider)
    return application


app = create_app()
