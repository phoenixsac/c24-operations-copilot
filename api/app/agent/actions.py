"""
AGT-6 / CORE-8 — the write path. docs/INVARIANTS.md D1, D2, D3, A4, A6.

Three properties, and each one is a separate row in `action_audit`:

  propose   result='pending_approval', executed_at NULL
  execute   result='executed',         approved_by set, executed_at set
  replay    result='replayed_noop',    nothing changed

They are separate rows rather than one row being updated because the table is
append-only — no UPDATE or DELETE grant exists (A4). That constraint turns out
to be a feature: the log is not "what the state is now", it is "what was asked
for, by whom, and what happened", and each of those is an event.

The three are joined by `idempotency_key`, which is derived, never generated:
`uuid5(action, order, rule)`. The same proposal computed twice yields the same
key, so a replay is recognisable without anyone having to remember a token.

WHAT IS NOT HERE. There is no path that executes without an approval row, and
no path where the approver is the proposer's session by default. The model
cannot reach any of it: it selects an `ActionId` from a closed enum and that is
the whole of its involvement (J1).
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from app.core.ir import ActionId
from app.db import Sql
from app.session import Role, Session


class NotPermitted(Exception):
    """Authorisation failed at execute. Carries why, for the audit row."""


class NoProposal(Exception):
    """Nothing to approve. An approval with no proposal is not an approval."""


def idempotency_key(action: str, order_id: int | None, rule_id: str) -> str:
    """
    Deterministic: the same (action, subject, cause) always yields the same key.

    Derived rather than random so two independent proposals for the same thing
    collide on purpose. A random key would make every retry a new action, which
    is the failure D2 exists to prevent.
    """
    return str(uuid.uuid5(
        uuid.NAMESPACE_URL, f"copilot:{action}:{order_id or 0}:{rule_id}"
    ))


async def record_proposal(
    sql: Sql, session: Session, *, answer_id: str, proposal: dict,
    rule_id: str, rule_version: int, order_id: int | None, ticket_id: str | None,
) -> None:
    """
    Persist a proposal so it can be approved later, possibly by someone else.

    `ON CONFLICT DO NOTHING` on the key: proposing the same action twice is one
    proposal, not two. Asking the same question twice must not queue two
    refunds.
    """
    await sql.all(
        """
        INSERT INTO action_audit
          (id, answer_id, order_id, ticket_id, action, proposal, proposed_by,
           rule_id, rule_version, idempotency_key, result, city_code, region)
        SELECT $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,'pending_approval',$11,$12
        WHERE NOT EXISTS (
            SELECT 1 FROM action_audit WHERE idempotency_key = $10
        )
        """,
        f"aud_{uuid.uuid4().hex[:8]}", answer_id, order_id, ticket_id,
        proposal["action"], json.dumps(proposal), session.user_id,
        rule_id, rule_version, proposal["idempotency_key"],
        session.city_code, session.region,
    )


async def find_proposal(sql: Sql, proposal_id: str, key: str) -> dict | None:
    """
    The pending proposal for this key.

    RLS already scoped the read, so a proposal from another city is simply not
    here — the caller sees "no proposal", which is the same answer it would get
    for one that never existed. ADR-001.
    """
    return await sql.one(
        """
        SELECT id, answer_id, order_id, ticket_id, action, proposal,
               proposed_by, rule_id, rule_version, idempotency_key, result
        FROM action_audit
        WHERE idempotency_key = $1
        ORDER BY CASE result WHEN 'executed' THEN 0
                             WHEN 'pending_approval' THEN 1 ELSE 2 END
        LIMIT 1
        """,
        key,
    )


def check_permitted(session: Session, action: str, amount_inr: float) -> None:
    """
    Authorisation, re-checked at execute and not trusted from the proposal. D3.

    The proposal was authored under someone else's session — often literally, in
    the case that matters, where an L1 proposes and a supervisor approves. A
    gate that reads the proposer's permissions is not a gate.
    """
    if ActionId(action) not in session.permitted_actions:
        raise NotPermitted(
            f"{session.role.value} is not permitted to perform {action}"
        )
    if action == ActionId.REFUND.value and amount_inr > session.refund_limit_inr:
        raise NotPermitted(
            f"₹{amount_inr:,.0f} is above the ₹{session.refund_limit_inr:,} "
            f"limit for {session.role.value}"
        )


async def execute(sql: Sql, session: Session, row: dict) -> dict:
    """
    Perform the action, then write the audit row. In that order, and in one
    transaction — `with_session` holds it open, so a failure after the effect
    but before the log rolls both back rather than leaving an unlogged change.
    """
    proposal = row["proposal"]
    if isinstance(proposal, str):
        proposal = json.loads(proposal)
    params = proposal.get("params") or {}
    amount = float(params.get("amount_inr") or 0)

    check_permitted(session, row["action"], amount)
    result = await _perform(sql, session, row, params)

    await sql.all(
        """
        INSERT INTO action_audit
          (id, answer_id, order_id, ticket_id, action, proposal, proposed_by,
           approved_by, rule_id, rule_version, idempotency_key, executed_at,
           result, city_code, region)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,now(),'executed',$12,$13)
        """,
        f"aud_{uuid.uuid4().hex[:8]}", row["answer_id"], row["order_id"],
        row["ticket_id"], row["action"], json.dumps(proposal),
        row["proposed_by"], session.user_id, row["rule_id"], row["rule_version"],
        row["idempotency_key"], session.city_code, session.region,
    )
    return result


async def _perform(sql: Sql, session: Session, row: dict, params: dict) -> dict:
    """
    The effect itself.

    Only `refund` has a real effect in this build — it is the one the fixture
    exercises end to end, and the one where getting idempotency wrong costs
    actual money. The rest are audited and reported as recorded-not-performed,
    which is the honest state: an action that claims to have escalated to the
    RTO while doing nothing is worse than one that says it did nothing.
    """
    action = row["action"]

    if action == ActionId.REFUND.value:
        refund_id = f"RF-{row['idempotency_key'][:8]}"
        await sql.all(
            """
            INSERT INTO refund (id, order_id, payment_id, amount, status,
                                idempotency_key, created_at, city_code, region)
            SELECT $1, $2, p.id, $3, 'pending', $4, now(), $5, $6
            FROM payment p
            WHERE p.order_id = $2 AND p.kind = 'full'
            ON CONFLICT (idempotency_key) DO NOTHING
            """,
            refund_id, row["order_id"], params.get("amount_inr") or 0,
            row["idempotency_key"], session.city_code, session.region,
        )
        return {"effect": "refund_created", "refund_id": refund_id}

    return {"effect": "recorded_only", "note": (
        f"{action} is audited but has no integration in this build; "
        "no external system was called"
    )}


async def replay(sql: Sql, session: Session, original: dict) -> dict:
    """
    A second approval of an already-executed key. Logged, changes nothing.

    Recorded rather than ignored: two people approving the same refund is worth
    knowing about even though only one refund exists. D2.
    """
    await sql.all(
        """
        INSERT INTO action_audit
          (id, answer_id, order_id, ticket_id, action, proposal, proposed_by,
           approved_by, rule_id, rule_version, idempotency_key, executed_at,
           result, city_code, region)
        SELECT $1, answer_id, order_id, ticket_id, action, proposal, proposed_by,
               $2, rule_id, rule_version, idempotency_key, now(),
               'replayed_noop', city_code, region
        FROM action_audit WHERE id = $3
        """,
        f"aud_{uuid.uuid4().hex[:8]}", session.user_id, original["id"],
    )
    proposal = original["proposal"]
    if isinstance(proposal, str):
        proposal = json.loads(proposal)
    return {"effect": "replayed_noop", "original_action": original["action"],
            "original_proposal": proposal}
