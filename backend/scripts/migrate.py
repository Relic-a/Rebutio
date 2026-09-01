import asyncio
import glob
import os
import sys
from sqlalchemy import text

# Ensure project and backend roots are in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.app.config import settings
from backend.app.models.db import Base
from backend.app.persistence.db import engine, normalized_url


async def run_postgres_migrations(conn):
    # Ensure migration tracking table exists
    await conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS public.schema_migrations (
                version VARCHAR(255) PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            """
        )
    )

    res = await conn.execute(text("SELECT version FROM public.schema_migrations;"))
    applied = set(row[0] for row in res.fetchall())

    # Find SQL migration files
    migrations_dir = os.path.join(PROJECT_ROOT, "migrations")
    if not os.path.exists(migrations_dir):
        print(f"[!] Migrations directory not found at: {migrations_dir}")
        return

    sql_files = sorted(glob.glob(os.path.join(migrations_dir, "*.sql")))
    if not sql_files:
        print("[!] No .sql migration files found.")
        return

    applied_count = 0
    for file_path in sql_files:
        version = os.path.basename(file_path)
        if version in applied:
            print(f"[-] Migration already applied: {version}")
            continue

        print(f"[*] Applying SQL migration: {version} ...")
        with open(file_path, "r", encoding="utf-8") as f:
            sql_content = f.read()

        # Execute migration SQL script (including tables, RLS policies, storage buckets)
        raw_conn = await conn.get_raw_connection()
        if hasattr(raw_conn, "driver_connection") and hasattr(raw_conn.driver_connection, "execute"):
            await raw_conn.driver_connection.execute(sql_content)
        else:
            await conn.execute(text(sql_content))

        # Record migration
        await conn.execute(
            text("INSERT INTO public.schema_migrations (version) VALUES (:ver);"),
            {"ver": version},
        )
        print(f"[✓] Successfully applied migration: {version}")
        applied_count += 1

    print(f"[✓] Migration run complete. {applied_count} new migration(s) applied.")


async def run_sqlite_schema(conn):
    print("[*] SQLite target detected: synchronizing SQLAlchemy metadata for local/test mode...")
    await conn.run_sync(Base.metadata.create_all)
    print("[✓] SQLite schema synchronization completed successfully.")


async def run_migrations():
    is_postgres = "postgresql" in normalized_url
    target_type = "PostgreSQL" if is_postgres else "SQLite"
    print(f"[*] Target Database ({target_type}): {normalized_url.split('@')[-1] if '@' in normalized_url else normalized_url}")

    async with engine.begin() as conn:
        if is_postgres:
            await run_postgres_migrations(conn)
        else:
            await run_sqlite_schema(conn)

    print("[✓] Schema migration completed successfully.")


if __name__ == "__main__":
    asyncio.run(run_migrations())
