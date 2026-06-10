import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.exception_handlers import register_exception_handlers
from app.core.logging import set_request_id, setup_logging
from app.core.openapi import OPENAPI_DESCRIPTION, configure_openapi
from app.core.redis import check_redis, close_redis
from app.db.session import check_postgres, engine
from app.schemas.response import fail

settings = get_settings()
setup_logging(settings)
logger = logging.getLogger(__name__)
access_logger = logging.getLogger("app.access")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if await check_postgres():
        logger.info("postgres_startup_check_ok")
    else:
        logger.error("postgres_startup_check_failed")

    if await check_redis():
        logger.info("redis_startup_check_ok")
    else:
        logger.error("redis_startup_check_failed")

    yield
    await close_redis()
    await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Go4Ride API",
        version="0.2.0",
        description=OPENAPI_DESCRIPTION,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )
    configure_openapi(app, settings)
    register_exception_handlers(app)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_logging_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        set_request_id(request_id)

        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)

        response.headers["X-Request-ID"] = request_id

        if request.url.path != "/health":
            status_code = response.status_code
            if status_code >= 500:
                level = logging.ERROR
            elif status_code >= 400:
                level = logging.WARNING
            else:
                level = logging.INFO
            access_logger.log(
                level,
                "request_completed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                    "client_ip": request.client.host if request.client else None,
                },
            )

        return response

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("unhandled_error")
        body = fail("Internal server error", "INTERNAL_ERROR")
        return JSONResponse(status_code=500, content=body.model_dump())

    @app.get("/health", tags=["health"], summary="Health check")
    async def health():
        """Liveness probe for load balancers and Render."""
        return {"status": "ok"}

    @app.get("/ready", tags=["health"], summary="Readiness check")
    async def ready():
        """Readiness probe — verifies Postgres and Redis connectivity."""
        postgres_ok = await check_postgres()
        redis_ok = await check_redis()
        body = {
            "status": "ok" if postgres_ok and redis_ok else "degraded",
            "postgres": "ok" if postgres_ok else "failed",
            "redis": "ok" if redis_ok else "failed",
        }
        if not postgres_ok:
            logger.error("readiness_check_failed", extra={"component": "postgres"})
        if not redis_ok:
            logger.error("readiness_check_failed", extra={"component": "redis"})
        status_code = 200 if postgres_ok and redis_ok else 503
        return JSONResponse(status_code=status_code, content=body)

    app.include_router(api_router)
    return app


app = create_app()
