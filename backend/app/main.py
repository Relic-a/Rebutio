import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.bootstrap import router as bootstrap_router
from backend.app.api.debates import router as debates_router
from backend.app.api.health import router as health_router
from backend.app.api.onboarding import router as onboarding_router
from backend.app.api.path import router as path_router
from backend.app.api.progress import router as progress_router
from backend.app.api.review import router as review_router
from backend.app.api.sessions import router as sessions_router
from backend.app.api.settings import router as settings_router
from backend.app.config import settings
from backend.app.persistence.db import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("rebutio.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing Rebutio database...")
    await init_db()
    logger.info("Rebutio database initialized.")
    yield
    logger.info("Rebutio backend shutting down.")


app = FastAPI(
    title="Rebutio API",
    description="Backend API for Rebutio Spoken-English Debate Learning Application",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS Configuration
origins = [
    settings.FRONTEND_ORIGIN,
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True,
    )
