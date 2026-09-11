"""
Database access.

Everything goes through `with_session`. There is no other way to reach the pool,
and that is deliberate: the RLS session variables must be set inside the same
transaction as the query, or a pooled connection silently carries one request's
scope into the next.

`set_config(..., is_local=True)` rather than string interpolation or a bare
`SET` — the setting is scoped to the transaction and cannot leak.
docs/DESIGN.md §9 calls this out as the detail most likely to be got wrong.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, AsyncIterator

import asyncpg

if TYPE_CHECKING:
    from app.session import Session

# app_user, never postgres. RLS is bypassed by superusers and table owners, so
# connecting as either would make every isolation test pass for the wrong
# reason. docs/DOMAIN_v2.md §6.
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgres://app_user:app_user@localhost:5432/copilot"
)

# The SELECT-only role behind the query console. E7.
READONLY_DATABASE_URL = os.getenv(
    "READONLY_DATABASE_URL",
    "postgres://app_readonly:app_readonly@localhost:5432/copilot",
)

_pool: asyncpg.Pool | None = None
_ro_pool: asyncpg.Pool | None = None


async def connect() -> None:
    global _pool, _ro_pool
    _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)
    _ro_pool = await asyncpg.create_pool(READONLY_DATABASE_URL, min_size=1, max_size=4)


async def disconnect() -> None:
    if _pool:
        await _pool.close()
    if _ro_pool:
        await _ro_pool.close()


def pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("pool not initialised")
    return _pool


class Sql:
    """
    Thin wrapper so query code reads the same as the SQL it runs.

    Rows come back as plain dicts because asyncpg Records are not JSON
    serialisable and Pydantic will not coerce them.
    """

    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def all(self, text: str, *args: Any) -> list[dict]:
        return [dict(r) for r in await self._conn.fetch(text, *args)]

    async def one(self, text: str, *args: Any) -> dict | None:
        row = await self._conn.fetchrow(text, *args)
        return dict(row) if row else None

    async def val(self, text: str, *args: Any) -> Any:
        return await self._conn.fetchval(text, *args)


@asynccontextmanager
async def with_session(
    session: "Session", *, readonly: bool = False
) -> AsyncIterator[Sql]:
    """
    Opens a transaction, applies the caller's scope, yields a query handle.

    The scope comes from the session and nothing else. No query in this codebase
    accepts a city_code from the client, because the moment one does the
    boundary moves out of the database and into whoever remembered to filter.
    """
    target = _ro_pool if readonly else _pool
    if target is None:
        raise RuntimeError("pool not initialised")

    async with target.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.city_code', $1, true)", session.city_code
            )
            await conn.execute(
                "SELECT set_config('app.region', $1, true)", session.region
            )
            await conn.execute(
                "SELECT set_config('app.role', $1, true)", session.role.value
            )
            if readonly:
                await conn.execute("SET LOCAL statement_timeout = 5000")
            yield Sql(conn)


async def healthy() -> bool:
    try:
        if _pool is None:
            return False
        await _pool.fetchval("SELECT 1")
        return True
    except Exception:
        return False
