"""
Session resolution.

The copilot has no identity of its own; it executes as the calling agent under
delegated authority and can never exceed what that agent could do by hand
(docs/INVARIANTS.md D4). So there is no service account here, and no credential
that outranks the caller.

Auth itself is stubbed to a header-supplied actor id, per docs/SCOPE.md §3 — the
delegation model is the point, not the login page. The important property
survives the stub: the scope is looked up **server-side from the actor row**,
never read off the request. A client that sends `X-City-Code: blr` changes
nothing.
"""

from __future__ import annotations

import os
from enum import Enum

from fastapi import Header, HTTPException
from pydantic import BaseModel

from app.core.ir import ActionId
from app import db


class Role(str, Enum):
    L1_AGENT = "l1_agent"
    SUPERVISOR = "supervisor"
    COPILOT_READONLY = "copilot_readonly"


class Session(BaseModel):
    user_id: str
    name: str
    role: Role
    city_code: str
    region: str
    permitted_actions: list[ActionId]
    refund_limit_inr: int


_L1_ACTIONS = [
    ActionId.ESCALATE_RTO, ActionId.REPLAY_WEBHOOK, ActionId.NOTIFY_CUSTOMER_DELAY,
    ActionId.SCHEDULE_DELIVERY, ActionId.CALL_CUSTOMER, ActionId.RECONCILE,
    ActionId.ASSIGN_NOW, ActionId.REQUEST_IDENTIFIER, ActionId.AUTO_FOLLOWUP,
    ActionId.REFUND,
]

# docs/README_v3.md §Authentication — two human roles, one copilot role.
ROLE_GRANTS: dict[Role, tuple[list[ActionId], int]] = {
    Role.L1_AGENT: (_L1_ACTIONS, 25_000),
    Role.SUPERVISOR: (
        _L1_ACTIONS + [
            ActionId.FREEZE_AND_REVIEW, ActionId.SUPERVISOR_EXCEPTION,
            ActionId.CANCEL_LATER_ORDER, ActionId.ROUTE_TO_SELLSIDE,
            ActionId.ESCALATE_SUPERVISOR, ActionId.REOPEN_FOR_AUDIT,
        ],
        10_000_000,
    ),
    Role.COPILOT_READONLY: ([], 0),
}

DEFAULT_ACTOR = os.getenv("DEFAULT_ACTOR", "u_priya")


async def resolve_session(x_actor_id: str | None = Header(default=None)) -> Session:
    """
    FastAPI dependency. Resolves the actor from the database.

    Note the query runs on an unscoped connection: `app_actor` carries no RLS
    policy, because you have to be able to look up who you are before you know
    what you can see.
    """
    actor_id = (x_actor_id or "").strip() or DEFAULT_ACTOR
    row = await db.pool().fetchrow(
        "SELECT id, name, role, city_code, region FROM app_actor WHERE id = $1", actor_id
    )
    if row is None:
        raise HTTPException(status_code=401, detail=f"unknown actor: {actor_id}")

    role = Role(row["role"])
    actions, limit = ROLE_GRANTS[role]
    return Session(
        user_id=row["id"],
        name=row["name"],
        role=role,
        city_code=row["city_code"],
        region=row["region"],
        permitted_actions=actions,
        refund_limit_inr=limit,
    )
