# Domain Model

Eleven entities plus an audit log — twelve tables. Deliberately small: enough to produce every failure mode under test, nothing more.

`app_actor` and `conversation_turn` also exist in the schema. They are infrastructure (session identity, multi-turn state per DESIGN.md §5), not domain entities, and are not counted in the twelve.

Storage is **Postgres 16** with row-level security. See §6.

---

## 1. Entities

```
customer         id, name, phone, city_code, region
vehicle          id, reg_no, make, model, year, km, listing_status
order            id, customer_id, vehicle_id, state, city_code, region,
                 created_at, updated_at
order_event      id, order_id, from_state, to_state, actor, reason, at   ← append-only, source of truth
payment          id, order_id, kind(token|full|payout), amount, status, txn_id, captured_at
refund           id, order_id, payment_id, amount, status, idempotency_key, created_at
rc_case          id, order_id, vehicle_id, status, blocked_reason, opened_at
refurb_job       id, vehicle_id, status, blocked_reason, promised_at, completed_at
delivery         id, order_id, slot_at, status, attempt_count, courier_ref
ticket           see §3 — the unit of work
ticket_message   id, ticket_id, direction, channel, author, body, injection_flagged, at   ← see note
action_audit     id, answer_id, proposal, proposed_by, approved_by,
                 rule_id, idempotency_key, executed_at, result
```

> **`ticket_message` is an addition to the original eleven.** `ticket` gave one
> `channel` and one `body`, but three things here already assume a thread:
> `first_response_at` implies a reply exists, reopen loops imply further contact,
> and marking untrusted content per *field* (J5) wants each inbound message
> flagged individually rather than one concatenated blob. `ticket.body` stays as
> a denormalised copy of the first inbound message so the queue list needs no
> join. `conversation_turn` (DESIGN.md §5) is the other table in the schema and
> is operator-side, not customer-side.

### Three properties that drive the design

**`order_event` is the source of truth, not `order.state`.** The state column is a materialised convenience. When the two disagree that's a real defect — detectable as `state_ledger_mismatch`, and seeded.

**Three units, not one.** An `order` is a transaction. A `vehicle` has a life across many orders (bought, refurbished, sold, returned, relisted). A `ticket` is the unit of work. "What's the status" is ambiguous unless the intended one is known, so entity resolution (reg_no → vehicle → orders, or ticket → order) is a feature rather than a bolt-on.

**`ticket.body` is untrusted.** Written by people outside the company, lands in the model's context window, treated as an adversarial surface everywhere it appears.

---

## 2. Order state machine

```
CREATED → TOKEN_PAID → FULL_PAID → REFURB_DONE → RC_DONE
        → DISPATCH_SCHEDULED → OUT_FOR_DELIVERY → DELIVERED
        → RETURN_WINDOW_OPEN → CLOSED
                            ↘ RETURN_REQUESTED → REFUNDED
```

Sell-side is stubbed to two states (`SELLER_PAYOUT_PENDING`, `SELLER_PAYOUT_DONE`) so cross-seam blockers exist without building the funnel.

---

## 3. Ticket — the unit of work

```
ticket
  id, order_id?, customer_id, channel, subject, body,
  state, priority, assigned_to, city_code, region,
  created_at, first_response_at, resolved_at,
  resolution_code, resolved_by, resolution_evidence (jsonb)
```

```
OPEN → ASSIGNED → IN_PROGRESS ──┬─→ AWAITING_CUSTOMER ─┐
                                └─→ AWAITING_INTERNAL ──┤
                                                        ▼
                                                    RESOLVED → CLOSED
                                                        ↑  │
                                                        └──┴─ REOPENED
```

`order_id` is nullable on purpose — customers write "my Swift hasn't arrived" with no order number.

`resolved_by` is an enum (`agent` | `copilot_auto`), never blank. Resolution without `resolution_evidence` is itself a detectable defect. Agent resolutions attach the copilot's `rule_id` and evidence automatically, so every close is auditable.

**Tier 2 auto-resolution** is permitted only when shape is `lookup`, zero rules fired, one entity resolved, read-only, no money, and intent matches an allowlisted template. A reopened ticket is force-assigned to a human — auto-reply never gets a second attempt.

---

## 4. Invariants → rules

Each invariant, when violated, is a named rule. This table is the rules-engine spec.

| rule_id | Invariant violated | Blocking entity | Suggested action |
|---|---|---|---|
| `payment_capture_lag` | Payment captured, order state not advanced >30m | payment | replay_webhook |
| `rc_transfer_stall` | FULL_PAID >72h, rc_case not done | rc_case | escalate_rto |
| `refurb_overrun` | refurb_job past promised_at | refurb_job | notify_customer_delay |
| `delivery_slot_missing` | RC_DONE >24h, no delivery row | — | schedule_delivery |
| `delivery_attempts_exhausted` | delivery.attempt_count ≥ 3 | delivery | call_customer |
| `refund_duplication` | >1 refund for same payment_id | refund | freeze_and_review |
| `seller_payout_hold` | Linked sell-side order stuck on KYC | payment(payout) | route_to_sellside |
| `inventory_double_allocation` | vehicle_id on 2 live orders | vehicle | cancel_later_order |
| `return_window_boundary` | Return requested within ±24h of expiry | — | supervisor_exception |
| `state_ledger_mismatch` | order.state ≠ last order_event.to_state | order_event | reconcile |
| `ticket_first_response_breach` | OPEN past first-response SLA | ticket | assign_now |
| `ticket_resolved_without_cause` | RESOLVED with no rule_id or evidence | ticket | reopen_for_audit |
| `ticket_reopen_loop` | Reopened ≥2 times | ticket | escalate_supervisor |
| `ticket_orphaned` | No order_id, resolution attempted | ticket | request_identifier |
| `ticket_stale_blocked` | AWAITING_CUSTOMER >7d, no follow-up | ticket | auto_followup |

---

## 5. Scoping model

Cars24 is B2C, so there is no tenant in the SaaS sense. The isolation axis is **operational**: `city_code` primary, `region` for supervisor rollup.

| Role | Sees | Can |
|---|---|---|
| `l1_agent` | Own city | Read, ask, propose, resolve, refund ≤ ₹25k |
| `supervisor` | Own region | Plus approve > ₹25k, policy exceptions, query console |
| `copilot_readonly` | Ticket in context | Lookup only, no writes (Tier 2) |

Rationale: data minimisation between employees, bounded PII exposure if an account is compromised, and traceable insider risk — not a wall between customers. Partner-dealer B2B would extend the same mechanism and is out of scope.

---

## 6. Row-level security

Every scoped table carries `city_code` and `region` and enables RLS:

```sql
ALTER TABLE tickets ENABLE ROW LEVEL SECURITY;

CREATE POLICY city_scope ON tickets
  USING (
    city_code = current_setting('app.city_code')
    OR (current_setting('app.role') = 'supervisor'
        AND region = current_setting('app.region'))
  );
```

Session variables are set inside the request transaction, immediately after auth:

```sql
SET LOCAL app.city_code = 'mum';
SET LOCAL app.role      = 'l1_agent';
```

- Connect as a dedicated `app_user`. RLS is bypassed by table owners and superusers, so tests otherwise pass for the wrong reason.
- Repository-layer predicates stay in place as defence in depth and to keep intent readable.
- Query console uses a `SELECT`-only role, `statement_timeout = 5s`, 500-row cap, every query logged.

A missed filter now returns zero rows rather than everyone's rows.

---

## 7. Seed plan

60 orders plus tickets. Fully deterministic — no RNG at all, so a re-seed is byte-identical (C7). Implemented in `db/init/03_seed.sql`, which asserts the counts on boot.

| Bucket | Count | Purpose |
|---|---|---|
| Healthy | 40 | Background noise so aggregates are meaningful |
| Broken | 18 | ≥1 clean instance per rule; 3 with two rules firing at once |
| Unanswerable | 2 | Correct output is refusal |
| Injection | 1 ticket | `ticket.body` contains an injection attempt |

Tickets span every state, including some with null `order_id`, some Tier-2 eligible, and some reopened twice. Three cities across two regions (`mum`/`pun` in west, `blr` in south), two human users per city.

---

## 8. Not modelled

Financing and loans, insurance, test drives, inspection reports, hub and yard slots, transport legs, agent rosters, warranty, partner-dealer accounts. Each adds tables without adding a new class of failure to reason about.
