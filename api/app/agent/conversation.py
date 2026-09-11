"""
AGT-7 — the conversation store. docs/DESIGN.md §7, ADR-010.

Four components per turn, and the fourth is the interesting one:

  1. `operator_text`   the operator's own words, bounded to the recent window
  2. `ir`              the structured plan — shape, entities, draft style
  3. `resolved_entities` stable handles, so "it" survives a rephrasing
  4. `result_digest`   rule ids, cited record ids, a state hash — NOT the results

**No model prose is ever stored or re-sent.** That is the whole design. A
synthesiser sentence is an output, and feeding it back in makes a hallucination
an input to the next turn — which is how a small error becomes the conversation's
premise. `verdict`, `explanation` and any draft are deliberately absent from
every column here.

The digest is what makes "and now?" answerable without carrying results. It
holds *which* rules fired and a hash of the state they fired against, so a later
turn can tell that something changed and must be recomputed — while being
structurally unable to answer from the old values, because it does not have them.

Bounded on read, not on write. Every turn is kept (the table is the audit trail
of what was asked); only the last few are ever loaded, which keeps the prompt
cost flat regardless of how long a thread runs. §7, D5.

Turns hang off a `conversation`, not off a ticket (ADR-033). Two reasons: a
console-level thread is about the whole book and has no ticket to hang from,
and "new session" has to be possible without deleting the record of what was
asked.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from app.core.ir import EntityRef, EntityType, QueryShape
from app.db import Sql

# How many turns are carried into a new one. Asserted rather than derived — the
# honest way to set it is to run the multi-turn cases at 1, 3 and 5 and see
# where answers stop improving, which needs more multi-turn cases than the
# fixture currently has. docs/IMPL.md §11.
WINDOW = 3

# ADR-011. A long thread is otherwise an unbounded loop of individually-legal
# requests, each one reasonable and the total unbounded.
MAX_TURNS = 20


class TurnCapExceeded(Exception):
    """Not an error — a boundary. The operator starts a new thread."""


def state_hash(snap: dict) -> str:
    """
    A fingerprint of the fields the rules actually read.

    Deliberately NOT a hash of the whole snapshot. Hashing everything means an
    unrelated write — a ticket reassignment, a note added — reports as "this
    changed", and a drift signal that fires constantly is one nobody reads.
    `IMPL.md` carried this as an open gap; this is the resolution.

    Only rule-relevant fields go in, in a fixed order.
    """
    o = snap.get("order") or {}
    parts: list[Any] = [
        o.get("state"),
        str(o.get("updated_at")),
        sorted((p["id"], p["status"]) for p in snap.get("payments") or []),
        sorted((r["id"], r["status"]) for r in snap.get("refunds") or []),
        (snap.get("rc_case") or {}).get("status"),
        (snap.get("refurb") or {}).get("status"),
        (snap.get("delivery") or {}).get("status"),
        (snap.get("delivery") or {}).get("attempt_count"),
        sorted(snap.get("vehicle_live_orders") or []),
        (snap.get("seller_payout") or {}).get("status"),
        (snap.get("ticket") or {}).get("state"),
        (snap.get("ticket") or {}).get("reopen_count"),
    ]
    blob = json.dumps(parts, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


async def open_conversation(
    sql: Sql, *, ticket_id: str | None, actor_id: str,
    city_code: str, region: str,
) -> str:
    """
    The open conversation for this ticket, or the actor's console thread when
    `ticket_id` is None. Created on first use.

    `closed_at IS NULL` is the whole selector. Starting a new session stamps
    `closed_at` on the old one rather than deleting its turns — see `close`.
    """
    row = await sql.one(
        """
        SELECT id FROM conversation
        WHERE closed_at IS NULL
          AND actor_id = $1
          AND ticket_id IS NOT DISTINCT FROM $2
        ORDER BY started_at DESC
        LIMIT 1
        """,
        actor_id, ticket_id,
    )
    if row:
        return row["id"]

    conv_id = f"conv_{uuid.uuid4().hex[:12]}"
    await sql.all(
        "INSERT INTO conversation (id, ticket_id, actor_id, city_code, region) "
        "VALUES ($1, $2, $3, $4, $5)",
        conv_id, ticket_id, actor_id, city_code, region,
    )
    return conv_id


async def owned(sql: Sql, conversation_id: str, actor_id: str) -> dict | None:
    """
    Ownership check before a thread is read or continued.

    RLS scopes to a CITY, not to a person — two Mumbai agents pass the same
    policy. So a conversation id arriving from a client must be checked against
    the actor as well, or Priya could read Tariq's thread by guessing an id.
    This is the one place that distinction matters, because every other table is
    about the business rather than about a person's working notes.
    """
    return await sql.one(
        "SELECT id, ticket_id, actor_id, started_at, closed_at "
        "FROM conversation WHERE id = $1 AND actor_id = $2",
        conversation_id, actor_id,
    )


async def listing(sql: Sql, *, ticket_id: str | None, actor_id: str) -> list[dict]:
    """
    Every thread in this scope, newest first, for a sidebar.

    The title is derived from the first operator turn rather than stored. A
    stored title needs generating, and generating it is either a model call
    nobody asked for or a column that goes stale the moment the thread moves on.
    The first thing someone typed is what they will recognise.
    """
    rows = await sql.all(
        """
        SELECT c.id, c.started_at, c.closed_at,
               count(t.id)                AS turn_count,
               max(t.at)                  AS last_at,
               min(t.turn_index)          AS first_index,
               (ARRAY_AGG(t.operator_text ORDER BY t.turn_index))[1] AS title
        FROM conversation c
        LEFT JOIN conversation_turn t ON t.conversation_id = c.id
        WHERE c.actor_id = $1 AND c.ticket_id IS NOT DISTINCT FROM $2
        GROUP BY c.id, c.started_at, c.closed_at
        ORDER BY COALESCE(max(t.at), c.started_at) DESC
        """,
        actor_id, ticket_id,
    )
    return [
        {
            "id": r["id"],
            "title": (r["title"] or "Empty session")[:60],
            "turn_count": r["turn_count"],
            "started_at": r["started_at"],
            "last_at": r["last_at"] or r["started_at"],
            "closed": r["closed_at"] is not None,
        }
        for r in rows
    ]


async def close(sql: Sql, conversation_id: str) -> None:
    """
    End a thread without destroying it.

    Deliberately not a DELETE. `conversation_turn` is the record of what an
    agent asked the copilot about a ticket, and on a case that is later
    disputed that record is exactly what you want. Clearing the chat window is
    a UI convenience and is not worth losing it for. A4 does not cover this
    table, so deleting would be *allowed* — it is simply the wrong default.
    """
    await sql.all(
        "UPDATE conversation SET closed_at = now() "
        "WHERE id = $1 AND closed_at IS NULL",
        conversation_id,
    )


async def history(sql: Sql, conversation_id: str) -> list[dict]:
    """
    The whole thread, for display. Includes `rendered_answer`, which `load`
    deliberately excludes — this feeds a screen, not a prompt.
    """
    rows = await sql.all(
        "SELECT turn_index, operator_text, rendered_answer FROM conversation_turn "
        "WHERE conversation_id = $1 ORDER BY turn_index ASC",
        conversation_id,
    )
    for row in rows:
        if isinstance(row["rendered_answer"], str):
            row["rendered_answer"] = json.loads(row["rendered_answer"])
    return rows


async def load(sql: Sql, conversation_id: str) -> tuple[list[dict], int]:
    """
    Returns the recent window (oldest first) and the next turn index.

    Note the SELECT list: `rendered_answer` is NOT among the columns. That
    column exists so a reloaded page can show the thread the operator already
    saw, and the memory path must not be able to reach it — re-sending a past
    answer to the model is exactly what ADR-010 forbids, because it turns a
    hallucination into the next turn's premise. Keeping it out of this query is
    the enforcement, not a convention.
    """
    rows = await sql.all(
        """
        SELECT turn_index, operator_text, ir, resolved_entities, result_digest
        FROM conversation_turn
        WHERE conversation_id = $1
        ORDER BY turn_index DESC
        LIMIT $2
        """,
        conversation_id, WINDOW,
    )
    total = await sql.val(
        "SELECT COALESCE(max(turn_index), 0) FROM conversation_turn "
        "WHERE conversation_id = $1",
        conversation_id,
    )
    # asyncpg hands back `jsonb` as text unless a codec is registered, so these
    # arrive as strings and every `.get()` downstream would fail on them.
    # Decoded once here rather than defensively at each use site.
    for row in rows:
        for col in ("ir", "resolved_entities", "result_digest"):
            if isinstance(row[col], str):
                row[col] = json.loads(row[col])
    return list(reversed(rows)), int(total or 0) + 1


async def save(
    sql: Sql, *, conversation_id: str, ticket_id: str | None, turn_index: int,
    actor_id: str, operator_text: str, ir: dict, resolved_entities: list[dict],
    result_digest: dict, answer_id: str, city_code: str, region: str,
    rendered_answer: dict | None = None,
) -> None:
    """
    Append-only in practice; `ON CONFLICT DO NOTHING` because a retried request
    with the same turn index is the same turn, not a second one.
    """
    await sql.all(
        """
        INSERT INTO conversation_turn
          (conversation_id, ticket_id, turn_index, actor_id, operator_text, ir,
           resolved_entities, result_digest, answer_id, city_code, region,
           rendered_answer)
        VALUES ($1,$2,$3,$4,$5,$6::jsonb,$7::jsonb,$8::jsonb,$9,$10,$11,$12::jsonb)
        ON CONFLICT (conversation_id, turn_index) DO NOTHING
        """,
        conversation_id, ticket_id, turn_index, actor_id,
        # Bounded so one pasted email cannot dominate every later prompt.
        operator_text[:2000],
        json.dumps(ir), json.dumps(resolved_entities), json.dumps(result_digest),
        answer_id, city_code, region,
        json.dumps(rendered_answer) if rendered_answer is not None else None,
    )


def to_prior(rows: list[dict]) -> "PriorTurnLike | None":
    """
    Rebuild the carry object from stored turns.

    Reads the most recent turn for shape and draft style, and unions entities
    across the window — an entity named three turns ago is still what "it"
    refers to, while a shape is only ever the last one.
    """
    if not rows:
        return None

    from app.ask import PriorTurn

    entities: list[EntityRef] = []
    seen: set[tuple[str, str]] = set()
    flagged = False
    for row in rows:
        digest = row["result_digest"] or {}
        flagged = flagged or bool(digest.get("injection_flagged"))
        for e in row["resolved_entities"] or []:
            key = (e["type"], str(e["id"]))
            if key in seen or e["type"] not in {t.value for t in EntityType}:
                continue
            seen.add(key)
            entities.append(EntityRef(type=EntityType(e["type"]), id=e["id"]))

    last_ir = rows[-1]["ir"] or {}
    last_digest = rows[-1]["result_digest"] or {}
    shape = last_ir.get("shape")
    return PriorTurn(
        entities=entities,
        rule_ids=list(last_digest.get("rule_ids") or []),
        shape=QueryShape(shape) if shape in {s.value for s in QueryShape} else None,
        draft_style=last_ir.get("draft_style"),
        injection_flagged=flagged,
    )


# Import-cycle dodge: `ask` imports this module, so the annotation above cannot
# name PriorTurn directly at module level.
PriorTurnLike = Any
