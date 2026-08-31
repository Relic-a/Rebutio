from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings
from backend.app.persistence.db import get_db
from backend.app.services.ai.openrouter import openrouter_client
from backend.app.services.ai.router_com import router_com_client

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    return {"status": "healthy", "app": "rebutio-backend"}


@router.get("/ready")
async def readiness_check(db: AsyncSession = Depends(get_db)):
    db_ok = False
    try:
        res = await db.execute(text("SELECT 1"))
        db_ok = bool(res.scalar_one_or_none() == 1)
    except Exception:
        db_ok = False

    openrouter_configured = openrouter_client.is_configured
    router_com_configured = router_com_client.is_configured

    all_ready = db_ok and (openrouter_configured or router_com_configured)
    status_str = "ready" if all_ready else "degraded"

    return {
        "status": status_str,
        "app": "rebutio-backend",
        "checks": {
            "database": "ok" if db_ok else "error",
            "openrouter": "configured" if openrouter_configured else "missing_key",
            "router_com": "configured" if router_com_configured else "not_configured",
            "modal": "configured",
        },
    }
