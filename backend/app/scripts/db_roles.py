"""Least-privilege database role for the application (run by the `migrate` service after Alembic).

* migrations run as the database owner (DDL rights);
* api and worker connect as APP_DB_USER: only SELECT/INSERT/UPDATE/DELETE on application tables,
  no DDL, no TRUNCATE, no access to alembic_version, not a superuser.
Idempotent: creates the role if missing, re-applies the password from .env (so rotating
APP_DB_PASSWORD + redeploy just works) and the grants.
"""

import asyncio
import os
import re
import sys

import asyncpg

from app.core.config import get_settings

NAME_RE = re.compile(r"^[a-z_][a-z0-9_]{2,62}$")


async def main() -> int:
    s = get_settings()
    role = os.environ.get("APP_DB_USER", "")
    password = os.environ.get("APP_DB_PASSWORD", "")
    if not role or not password:
        print(
            "db_roles: APP_DB_USER / APP_DB_PASSWORD not set, the app will use the owner role",
            file=sys.stderr,
        )
        return 0
    if not NAME_RE.match(role) or role == s.postgres_user:
        print("db_roles: invalid APP_DB_USER", file=sys.stderr)
        return 1

    conn = await asyncpg.connect(
        host=s.postgres_host,
        port=s.postgres_port,
        user=s.postgres_user,
        password=s.postgres_password,
        database=s.postgres_db,
    )
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_roles WHERE rolname = $1", role)
        # Identifiers can't be bind parameters; the role name is validated by NAME_RE above.
        # The password goes through format('%L') on the server side, so it's quoted safely.
        verb = "ALTER" if exists else "CREATE"
        sql = await conn.fetchval(
            f"SELECT format('{verb} ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD %L', $1::text, $2::text)",
            role,
            password,
        )
        await conn.execute(sql)
        owner = s.postgres_user
        db = s.postgres_db
        statements = [
            f'REVOKE ALL ON DATABASE "{db}" FROM PUBLIC',
            f'GRANT CONNECT ON DATABASE "{db}" TO "{role}"',
            "REVOKE CREATE ON SCHEMA public FROM PUBLIC",
            f'GRANT USAGE ON SCHEMA public TO "{role}"',
            f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "{role}"',
            f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "{role}"',
            f'REVOKE ALL ON TABLE alembic_version FROM "{role}"',
            f'ALTER DEFAULT PRIVILEGES FOR ROLE "{owner}" IN SCHEMA public '
            f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "{role}"',
            f'ALTER DEFAULT PRIVILEGES FOR ROLE "{owner}" IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO "{role}"',
        ]
        async with conn.transaction():
            for stmt in statements:
                await conn.execute(stmt)
    finally:
        await conn.close()
    print(f"db_roles: role '{role}' is ready (DML only)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
