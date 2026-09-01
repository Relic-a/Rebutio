#!/usr/bin/env python3
"""
Rebutio Migration Runner.
Executes database migrations and schema sync against PostgreSQL or SQLite.
Usage:
    python backend/scripts/migrate.py
"""

import asyncio
import os
import sys

# Ensure backend root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.app.config import settings
from backend.app.models.db import Base
from backend.app.persistence.db import engine, init_db, normalized_url


async def run_migrations():
    print(f"[*] Target Database URL: {normalized_url}")
    print("[*] Applying Rebutio database schema migrations...")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    print("[✓] Schema migration completed successfully.")


if __name__ == "__main__":
    asyncio.run(run_migrations())
