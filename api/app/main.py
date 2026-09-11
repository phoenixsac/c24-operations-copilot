"""
HTTP API. Typed endpoints only; `/ask` is the sole natural-language surface.

Two properties hold across every route:

  1. The session is resolved server-side from the actor row. No handler reads a
     city_code, region or role off the request. docs/INVARIANTS.md E3.
  2. Every database call goes through `with_session`, which opens a transaction
     and applies the scope before the first query runs.
"""

from __future__ import annotations

import logging
import re
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from app import clock, db
from app.agent import actions, conversation
from app.ask import ask as run_ask
from app.model import gateway as mdl
from app.obs import langfuse_export
from app.data import queries as q
from app.session import Role, Session, resolve_session

log = logging.getLogger("copilot")
logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await db.connect()
    # Config is validated here, so a bad MODEL_ADAPTER or a missing API key
    # stops the container rather than surfacing as a degraded answer later.
    await mdl.connect()
    yield
    await mdl.disconnect()
    await db.disconnect()


app = FastAPI(title="Operations Copilot API", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Request models. Note what is absent: no actor, no city, no role. Scope is
# never accepted from the client.
# ---------------------------------------------------------------------------

class AskRequest(BaseModel):
    query: str
    ticket_id: str | None = None
    # Which thread to continue. Not history — an id, checked against the
    # caller's actor before anything is read. ADR-032 forbids the client
    # supplying conversation *content*; naming which of its own threads to use
    # is the same kind of claim as naming a ticket, and is verified the same way.
    conversation_id: str | None = None


class ResolveRequest(BaseModel):
    resolution_code: str
    answer_id: str


class QueryRequest(BaseModel):
    sql: str = Field(min_length=1)


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    """
    What is configured, not what is valid. Reports the model boundary so a
    demo running on the fake adapter is obvious from the outside — a console
    that looks identical whether or not a provider is wired up is a trap.
    """
    return {
        "ok": await db.healthy(),
        "model": mdl.status(),
        # A demo running on a pinned clock looks identical to one running live
        # until an age is wrong by a day. Say which it is.
        "clock": {
            "now": clock.now().isoformat(),
            "pinned": clock.is_pinned(),
        },
    }


@app.get("/session")
async def get_session(session: Session = Depends(resolve_session)):
    return session


@app.get("/tickets")
async def tickets(session: Session = Depends(resolve_session)):
    async with db.with_session(session) as sql:
        return await q.ticket_queue(sql, session)


@app.get("/tickets/{ticket_id}")
async def ticket(ticket_id: str, session: Session = Depends(resolve_session)):
    async with db.with_session(session) as sql:
        found = await q.ticket_detail(sql, ticket_id)
    # Out of scope and non-existent are indistinguishable from here, which is
    # the correct behaviour: a 404 that means "exists but not yours" is a leak.
    if not found:
        raise HTTPException(404, "not found")
    return found


@app.get("/tickets/{ticket_id}/records")
async def records(ticket_id: str, session: Session = Depends(resolve_session)):
    async with db.with_session(session) as sql:
        graph = await q.records_graph(sql, ticket_id)
    if not graph:
        raise HTTPException(404, "not found")
    return graph


@app.get("/cohorts")
async def cohorts(session: Session = Depends(resolve_session)):
    async with db.with_session(session) as sql:
        return await q.cohorts(sql)


@app.get("/cohorts/tickets")
async def ticket_cohorts(session: Session = Depends(resolve_session)):
    async with db.with_session(session) as sql:
        return await q.ticket_cohorts(sql)


@app.get("/audit")
async def audit(session: Session = Depends(resolve_session)):
    async with db.with_session(session) as sql:
        return await q.audit_log(sql)


@app.get("/query/schema")
async def query_schema(session: Session = Depends(resolve_session)):
    async with db.with_session(session) as sql:
        return await q.console_schema(sql)


@app.get("/query/saved")
async def saved_queries():
    """
    Each saved query is a rule from docs/DOMAIN_v2.md §4 expressed in SQL, so the
    console and the rules engine answer the same question the same way. No city
    predicate appears in any of them — RLS supplies that.
    """
    return [
        {"name": "Stuck in RC transfer", "sql": """SELECT o.id AS order_id, o.state, r.id AS rc_id,
       r.blocked_reason, o.city_code, t.id AS ticket_id
FROM orders o
JOIN rc_case r ON r.order_id = o.id
LEFT JOIN ticket t ON t.order_id = o.id
WHERE o.state = 'FULL_PAID' AND r.status <> 'done'
ORDER BY o.updated_at ASC"""},
        {"name": "Refund duplicates", "sql": """SELECT r.payment_id, count(*) AS refund_count, sum(r.amount) AS total
FROM refund r
GROUP BY r.payment_id
HAVING count(*) > 1
ORDER BY total DESC"""},
        {"name": "Deliveries missing a slot", "sql": """SELECT o.id AS order_id, o.state, o.city_code, o.updated_at
FROM orders o
LEFT JOIN delivery d ON d.order_id = o.id
WHERE d.id IS NULL
  AND o.state IN ('RC_DONE','REFURB_DONE')
  AND o.updated_at < now() - interval '24 hours'
ORDER BY o.updated_at ASC"""},
        {"name": "State disagrees with the ledger", "sql": """SELECT o.id AS order_id, o.state AS column_state, e.to_state AS ledger_state
FROM orders o
JOIN LATERAL (
  SELECT to_state FROM order_event WHERE order_id = o.id
  ORDER BY at DESC, id DESC LIMIT 1
) e ON true
WHERE o.state <> e.to_state"""},
    ]


# ---------------------------------------------------------------------------
# Ask
# ---------------------------------------------------------------------------

@app.get("/conversations")
async def get_conversation(
    ticket_id: str | None = None,
    conversation_id: str | None = None,
    session: Session = Depends(resolve_session),
):
    """
    A thread, for hydrating a screen.

    With `conversation_id`, that specific thread — including a closed one, which
    is what makes "closed, not deleted" mean something to a person rather than
    only to whoever can run SQL. Without it, the current open thread.

    Omit `ticket_id` for the console-level thread: the one about the whole book
    rather than one case.
    """
    async with db.with_session(session) as sql:
        if conversation_id:
            row = await conversation.owned(sql, conversation_id, session.user_id)
            # Same 404-not-403 rule as everywhere else: "exists but not yours"
            # is itself a disclosure. ADR-001.
            if not row:
                raise HTTPException(404, "not found")
            conv_id = row["id"]
            ticket_id = row["ticket_id"]
            closed = row["closed_at"] is not None
        else:
            conv_id = await conversation.open_conversation(
                sql, ticket_id=ticket_id, actor_id=session.user_id,
                city_code=session.city_code, region=session.region,
            )
            closed = False

        rows = await conversation.history(sql, conv_id)
        return {
            "conversation_id": conv_id,
            "ticket_id": ticket_id,
            "closed": closed,
            "turn_count": len(rows),
            "max_turns": conversation.MAX_TURNS,
            "turns": [
                {"turn_index": r["turn_index"],
                 "operator_text": r["operator_text"],
                 "answer": r["rendered_answer"]}
                for r in rows
            ],
        }


@app.get("/conversations/list")
async def list_conversations(
    ticket_id: str | None = None,
    session: Session = Depends(resolve_session),
):
    """Every thread in this scope, newest first. The sidebar's data."""
    async with db.with_session(session) as sql:
        return await conversation.listing(
            sql, ticket_id=ticket_id, actor_id=session.user_id,
        )


class NewConversationRequest(BaseModel):
    ticket_id: str | None = None


@app.post("/conversations/new")
async def new_conversation(
    body: NewConversationRequest,
    session: Session = Depends(resolve_session),
):
    """
    Start a fresh thread. The previous one is closed, not deleted — its turns
    remain queryable as the record of what was asked. ADR-033.
    """
    async with db.with_session(session) as sql:
        current = await conversation.open_conversation(
            sql, ticket_id=body.ticket_id, actor_id=session.user_id,
            city_code=session.city_code, region=session.region,
        )
        await conversation.close(sql, current)
        fresh = await conversation.open_conversation(
            sql, ticket_id=body.ticket_id, actor_id=session.user_id,
            city_code=session.city_code, region=session.region,
        )
        return {"conversation_id": fresh}


@app.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    session: Session = Depends(resolve_session),
):
    """
    Delete a thread. Really delete — the row goes, and its turns cascade.

    This reverses part of [ADR-033], which argued for closing rather than
    deleting on the grounds that "what an agent asked about a case" is worth
    keeping. That argument was weaker than it looked: `action_audit` is the
    audit trail, it is append-only, and it is a different table. Deleting a
    conversation destroys no record of anything that was *done* — every
    proposal, approval and execution survives untouched, with its actor and its
    idempotency key.

    What is lost is the operator's own working notes, which are theirs to
    discard. A chat history nobody can clear is a chat history people work
    around by never starting one.
    """
    async with db.with_session(session) as sql:
        row = await conversation.owned(sql, conversation_id, session.user_id)
        if not row:
            raise HTTPException(404, "not found")
        # ON DELETE CASCADE on conversation_turn.conversation_id removes the
        # turns; the FK is what makes this one statement rather than two.
        await sql.all("DELETE FROM conversation WHERE id = $1", conversation_id)
        return {"deleted": conversation_id}


@app.post("/ask")
async def ask(body: AskRequest, session: Session = Depends(resolve_session)):
    """
    Multi-turn, and the memory lives in the database rather than in the client.

    The request carries no history: a client that could supply its own
    conversation could also fabricate one, and "the previous turn resolved
    order 4110" is exactly the sentence that would walk a Mumbai agent into
    Pune data. History is loaded from `conversation_turn` under the same
    RLS-scoped transaction as everything else. E3, ADR-032.
    """
    async with db.with_session(session) as sql:
        if body.conversation_id:
            row = await conversation.owned(
                sql, body.conversation_id, session.user_id,
            )
            if not row:
                raise HTTPException(404, "not found")
            conv_id = row["id"]
            # Continuing a thread that was closed reopens it. Safe here in a way
            # it would not be in a system that carried results forward: every
            # turn re-runs the rules against current records, so an old thread
            # about an order that has since moved on recomputes rather than
            # repeating itself (eval M-02). The stored `state_hash` is what
            # makes the change detectable.
            if row["closed_at"] is not None:
                await sql.all(
                    "UPDATE conversation SET closed_at = NULL WHERE id = $1",
                    conv_id,
                )
        else:
            conv_id = await conversation.open_conversation(
                sql, ticket_id=body.ticket_id, actor_id=session.user_id,
                city_code=session.city_code, region=session.region,
            )
        history, turn_index = await conversation.load(sql, conv_id)
        if turn_index > conversation.MAX_TURNS:
            # A boundary, not an error. ADR-011: without it a long thread is an
            # unbounded loop of individually-legal requests. The client offers
            # "new session", which closes this thread rather than deleting it.
            raise HTTPException(
                status_code=429,
                detail=(
                    f"This conversation has reached {conversation.MAX_TURNS} turns. "
                    "Start a new session to continue."
                ),
            )

        # The gateway is passed in rather than imported inside `ask`, so a test
        # or an eval run can hand it a different adapter — or none, which takes
        # the F4 deterministic path through exactly the same code (ADR-014).
        answer = await run_ask(
            sql, session, body.query, body.ticket_id,
            gw=mdl.gateway(),
            prior=conversation.to_prior(history),
        )
        answer["turn_index"] = turn_index
        answer["conversation_id"] = conv_id

        # Exported after the answer is built and before it is returned, so a
        # slow or unreachable collector shows up as latency rather than as a
        # lost trace. Every failure path inside is swallowed — an observability
        # tool that can break the request it observes is worse than none.
        langfuse_export.export(
            answer.get("_trace_obj"),
            shape=answer.get("ir", {}).get("shape", "unknown"),
            refused=answer.get("refusal") is not None,
            model=answer.get("trace", {}).get("model", "unknown"),
        ) if answer.get("_trace_obj") else None
        answer.pop("_trace_obj", None)

        await conversation.save(
            sql,
            conversation_id=conv_id,
            ticket_id=body.ticket_id,
            turn_index=turn_index,
            actor_id=session.user_id,
            operator_text=body.query,
            ir={**answer.get("ir", {}), "draft_style": answer.get("draft_style")},
            resolved_entities=answer.get("ir", {}).get("entities", []),
            result_digest=answer.get("digest", {}),
            answer_id=answer["answer_id"],
            city_code=session.city_code,
            region=session.region,
            # Display only. Never read back into a prompt — `load` does not
            # select this column. ADR-033.
            rendered_answer=answer,
        )
        return answer


# ---------------------------------------------------------------------------
# Writes — proposed, approved, idempotent. All three, always.
# ---------------------------------------------------------------------------

@app.post("/tickets/{ticket_id}/assign")
async def assign(ticket_id: str, session: Session = Depends(resolve_session)):
    async with db.with_session(session) as sql:
        # The assignee is the caller. A client cannot assign work to someone
        # else by putting their id in the body — there is no body.
        row = await sql.one("""
            UPDATE ticket SET assigned_to = $1,
                   state = CASE WHEN state = 'OPEN' THEN 'ASSIGNED' ELSE state END,
                   first_response_at = COALESCE(first_response_at, now())
            WHERE id = $2 RETURNING assigned_to
        """, session.user_id, ticket_id)
    if not row:
        raise HTTPException(404, "not found")
    return {"assignee": session.name}


@app.post("/tickets/{ticket_id}/resolve")
async def resolve(ticket_id: str, body: ResolveRequest,
                  session: Session = Depends(resolve_session)):
    """
    Resolution requires a code and evidence. Closing with neither is itself a
    detectable defect (ticket_resolved_without_cause), so the API refuses to
    create one rather than relying on the UI to decline.

    Pydantic enforces both fields, so a request missing either never reaches
    this body — it is a 422 at the boundary.
    """
    async with db.with_session(session) as sql:
        row = await sql.one("""
            UPDATE ticket
            SET state = 'RESOLVED', resolved_at = now(), resolution_code = $1,
                resolved_by = 'agent', resolution_evidence = $2::jsonb
            WHERE id = $3 RETURNING state
        """, body.resolution_code,
             f'{{"answer_id":"{body.answer_id}","resolved_by":"{session.user_id}"}}',
             ticket_id)
    if not row:
        raise HTTPException(404, "not found")
    return {"state": "RESOLVED"}


@app.post("/tickets/{ticket_id}/reopen")
async def reopen(ticket_id: str, session: Session = Depends(resolve_session)):
    async with db.with_session(session) as sql:
        row = await sql.one("""
            UPDATE ticket SET state = 'REOPENED', reopen_count = reopen_count + 1,
                   resolved_at = NULL, resolved_by = NULL
            WHERE id = $1 RETURNING state
        """, ticket_id)
    if not row:
        raise HTTPException(404, "not found")
    return {"state": "REOPENED"}


@app.post("/actions/{proposal_id}/approve")
async def approve(proposal_id: str, session: Session = Depends(resolve_session),
                  idempotency_key: str | None = Header(default=None)):
    """
    Approve and execute. Three outcomes, and which one you get is decided by
    the log rather than by anything the caller says.

    Idempotent under the key the proposal carried: if that key has already
    executed, this records a no-op and changes nothing (D2). Authorisation is
    re-checked here against the *approver's* session, not inherited from the
    proposal — the case that matters is an L1 proposing and a supervisor
    approving, and a gate that reads the proposer's permissions is not a gate
    (D3).
    """
    if not idempotency_key:
        raise HTTPException(400, "Idempotency-Key header required")

    async with db.with_session(session) as sql:
        row = await actions.find_proposal(sql, proposal_id, idempotency_key)
        if row is None:
            # Never existed, or belongs to another city and RLS removed it.
            # Indistinguishable on purpose. ADR-001.
            raise HTTPException(404, "no matching proposal")

        if row["result"] == "executed":
            out = await actions.replay(sql, session, row)
            return {"executed": False, "result": "replayed_noop", **out}

        try:
            out = await actions.execute(sql, session, row)
        except actions.NotPermitted as exc:
            raise HTTPException(403, str(exc)) from exc

        return {"executed": True, "result": "executed",
                "idempotency_key": idempotency_key, **out}


# ---------------------------------------------------------------------------
# Query console
# ---------------------------------------------------------------------------

_SELECT_ONLY = re.compile(r"^\s*select\b", re.I)


@app.post("/query")
async def query_console(body: QueryRequest, session: Session = Depends(resolve_session)):
    """
    Supervisor only, on the SELECT-only role, 5s statement timeout, 500-row cap,
    every query logged. The connection itself cannot see out of scope, so no SQL
    rewriting is required whatever is typed. docs/README_v3.md §Storage.
    """
    if session.role is not Role.SUPERVISOR:
        raise HTTPException(403, "supervisor role required")

    text = body.sql.strip().rstrip(";")
    if not _SELECT_ONLY.match(text) or ";" in text:
        raise HTTPException(400, "only a single SELECT statement is permitted")

    started = datetime.now(timezone.utc)
    audit_id = f"aud_q_{uuid.uuid4().hex[:6]}"
    log.info("query-console actor=%s audit=%s sql=%s",
             session.user_id, audit_id, " ".join(text.split())[:200])

    async with db.with_session(session, readonly=True) as sql:
        rows = await sql.all(f"SELECT * FROM ({text}) q LIMIT 501")

    truncated = len(rows) > 500
    out = rows[:500]
    return {
        "columns": list(out[0].keys()) if out else [],
        "rows": [{k: ("" if v is None else str(v)) for k, v in r.items()} for r in out],
        # Rows *within scope*. There is deliberately no global count: the
        # connection cannot see the other rows, so it cannot count them either.
        "row_count": len(out),
        "ms": int((datetime.now(timezone.utc) - started).total_seconds() * 1000),
        "truncated": truncated,
        "audit_id": audit_id,
    }
