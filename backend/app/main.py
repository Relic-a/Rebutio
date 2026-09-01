from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.bootstrap import router as bootstrap_router
from backend.app.api.coach import router as coach_router
from backend.app.api.debates import router as debates_router
from backend.app.api.health import router as health_router
from backend.app.api.media import router as media_router
from backend.app.api.onboarding import router as onboarding_router
from backend.app.api.path import router as path_router
from backend.app.api.progress import router as progress_router
from backend.app.api.review import router as review_router
from backend.app.api.sessions import router as sessions_router
from backend.app.api.settings import router as settings_router
from backend.app.config import settings
from backend.app.observability.logging import get_logger, setup_logging
from backend.app.observability.middleware import RequestLoggingMiddleware
from backend.app.persistence.db import init_db

# Initialize structured logging centrally
setup_logging(
    log_level=settings.LOG_LEVEL,
    log_format=settings.LOG_FORMAT,
    log_ai_content=settings.LOG_AI_CONTENT,
)
logger = get_logger("rebutio.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Production security fail-closed sanity checks
    DEFAULT_DEV_KEY = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    DEFAULT_DEV_SESSION_SECRET = "rebutio-stable-dev-session-secret-key-32b"

    if settings.ENVIRONMENT == "production":
        # 1. Database check: must use PostgreSQL in production
        db_url = settings.DATABASE_URL.lower()
        if not ("postgresql" in db_url or "postgres" in db_url):
            raise RuntimeError("CRITICAL PRODUCTION CONFIGURATION ERROR: DATABASE_URL must be PostgreSQL in production!")

        # 2. Auth bypass check: dev auth bypass must be strictly disabled
        if settings.ALLOW_DEV_AUTH_BYPASS:
            raise RuntimeError("CRITICAL SECURITY VIOLATION: ALLOW_DEV_AUTH_BYPASS cannot be True in production!")

        # 3. JWT verification config check
        if not (settings.INSFORGE_JWT_SECRET or settings.INSFORGE_JWT_PUBLIC_KEY):
            raise RuntimeError("CRITICAL CONFIGURATION ERROR: Production requires InsForge JWT verification configuration (INSFORGE_JWT_SECRET or INSFORGE_JWT_PUBLIC_KEY)!")

        # 4. Storage credentials check: must use private INSFORGE_API_KEY
        if not settings.INSFORGE_API_KEY:
            raise RuntimeError("CRITICAL CONFIGURATION ERROR: Production requires private INSFORGE_API_KEY for server-side storage operations!")

        # 5. Encryption & session secret checks
        if not settings.REBUTIO_DATA_ENCRYPTION_KEY or settings.REBUTIO_DATA_ENCRYPTION_KEY == DEFAULT_DEV_KEY:
            raise RuntimeError("CRITICAL SECURITY VIOLATION: REBUTIO_DATA_ENCRYPTION_KEY must be configured with a secure key in production!")
        if not settings.REBUTIO_SESSION_SECRET or settings.REBUTIO_SESSION_SECRET == DEFAULT_DEV_SESSION_SECRET:
            raise RuntimeError("CRITICAL SECURITY VIOLATION: REBUTIO_SESSION_SECRET must be configured with a secure key in production!")

    # Log startup configuration safely without secrets
    db_type = "postgresql" if "postgresql" in settings.DATABASE_URL else "sqlite"
    logger.info(
        "app.started",
        environment="development" if "localhost" in settings.FRONTEND_ORIGIN else "production",
        database=db_type,
        openrouter_configured=bool(settings.OPENROUTER_API_KEY),
        router_configured=bool(settings.RAMP_ROUTER_API_KEY),
        modal_configured=bool(settings.MODAL_APP_NAME),
        log_level=settings.LOG_LEVEL,
        log_format=settings.LOG_FORMAT,
        ai_content_logging=settings.LOG_AI_CONTENT,
    )

    # Log model-role mapping safely
    logger.info(
        "app.model_configuration",
        debate_opponent=f"router:{settings.ROUTER_DEBATE_MODEL}" if settings.ROUTER_DEBATE_MODEL and settings.RAMP_ROUTER_API_KEY else f"openrouter:{settings.OPENROUTER_DEBATE_MODEL}",
        language_analysis=f"router:{settings.ROUTER_ANALYSIS_MODEL}" if settings.ROUTER_ANALYSIS_MODEL and settings.RAMP_ROUTER_API_KEY else f"openrouter:{settings.OPENROUTER_ANALYSIS_MODEL}",
        final_patch=f"openrouter:{settings.OPENROUTER_FINAL_PATCH_MODEL}",
        reviewer=f"router:{settings.ROUTER_REVIEW_MODEL}" if settings.ROUTER_REVIEW_MODEL and settings.RAMP_ROUTER_API_KEY else f"openrouter:{settings.OPENROUTER_REVIEW_MODEL}",
        topic_generator=f"router:{settings.ROUTER_TOPIC_MODEL}" if settings.ROUTER_TOPIC_MODEL and settings.RAMP_ROUTER_API_KEY else f"openrouter:{settings.OPENROUTER_TOPIC_MODEL}",
        transcription=f"openrouter:{settings.OPENROUTER_TRANSCRIPTION_MODEL}",
        speech=f"openrouter:{settings.OPENROUTER_TTS_MODEL}",
    )

    logger.info("db.init.started")
    await init_db()
    logger.info("db.init.completed")

    # Validate Router.com catalog at startup if configured
    from backend.app.services.ai.router_com import router_com_client
    if router_com_client.is_configured:
        try:
            available_models = await router_com_client.get_available_models()
            logger.info("router_com.catalog_validated", available_models_count=len(available_models))
            configured_models = [
                settings.ROUTER_DEBATE_MODEL,
                settings.ROUTER_ANALYSIS_MODEL,
                settings.ROUTER_REVIEW_MODEL,
                settings.ROUTER_TOPIC_MODEL,
            ]
            for m in configured_models:
                if m and m not in available_models:
                    logger.warning("router_com.model_not_in_catalog", model=m)
        except Exception as e:
            logger.warning("router_com.catalog_validation_failed", error=str(e))

    yield
    logger.info("app.stopped")


app = FastAPI(
    title="Rebutio API",
    description="Backend API for Rebutio Spoken-English Debate Learning Application",
    version="0.1.0",
    lifespan=lifespan,
)

# Correlation & Request Logging Middleware
app.add_middleware(RequestLoggingMiddleware)

# CORS Configuration
origins = [
    settings.FRONTEND_ORIGIN,
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:3002",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
    "http://127.0.0.1:3002",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"^https?:\/\/(localhost|127\.0\.0\.1)(:[0-9]+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API Routers
app.include_router(health_router)
app.include_router(bootstrap_router)
app.include_router(onboarding_router)
app.include_router(path_router)
app.include_router(debates_router)
app.include_router(sessions_router)
app.include_router(review_router)
app.include_router(progress_router)
app.include_router(settings_router)
app.include_router(coach_router)
app.include_router(media_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True,
    )
