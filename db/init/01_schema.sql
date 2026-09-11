-- Schema. docs/DOMAIN_v2.md §1.
--
-- Twelve tables plus the audit log and the conversation store.
--
-- DOMAIN_v2.md specifies eleven. `ticket_message` is a deliberate addition:
-- the model gave `ticket` a single `channel`/`body`, but three things in the
-- design already assume a thread — `first_response_at` implies a reply, reopen
-- loops imply further contact, and J4 (second-order injection) wants each
-- inbound message marked untrusted individually rather than one blob. See
-- docs/GLOSSARY.md. `conversation_turn` is specified in docs/DESIGN.md §5.
--
-- Every scoped table carries city_code and region, denormalised on purpose so
-- one RLS policy shape works everywhere (docs/DOMAIN_v2.md §6).
--
-- Column comments carry the PII classification from docs/INVARIANTS.md §H.
-- They are the source for the generated field table required by H12.

-- ---------------------------------------------------------------------------
-- Enums
-- ---------------------------------------------------------------------------

CREATE TYPE order_state AS ENUM (
  'CREATED', 'TOKEN_PAID', 'FULL_PAID', 'REFURB_DONE', 'RC_DONE',
  'DISPATCH_SCHEDULED', 'OUT_FOR_DELIVERY', 'DELIVERED',
  'RETURN_WINDOW_OPEN', 'CLOSED', 'RETURN_REQUESTED', 'REFUNDED',
  -- Sell-side is stubbed to two states so cross-seam blockers exist without
  -- building a second funnel. docs/DOMAIN_v2.md §2.
  'SELLER_PAYOUT_PENDING', 'SELLER_PAYOUT_DONE'
);

CREATE TYPE ticket_state AS ENUM (
  'OPEN', 'ASSIGNED', 'IN_PROGRESS', 'AWAITING_CUSTOMER',
  'AWAITING_INTERNAL', 'RESOLVED', 'CLOSED', 'REOPENED'
);

CREATE TYPE ticket_priority   AS ENUM ('low', 'normal', 'high', 'urgent');
CREATE TYPE payment_kind      AS ENUM ('token', 'full', 'payout');
CREATE TYPE payment_status    AS ENUM ('pending', 'captured', 'failed', 'refunded');
CREATE TYPE refund_status     AS ENUM ('pending', 'processing', 'completed', 'frozen');
CREATE TYPE rc_status         AS ENUM ('open', 'in_progress', 'blocked', 'done');
CREATE TYPE refurb_status     AS ENUM ('scheduled', 'in_progress', 'blocked', 'completed');
CREATE TYPE delivery_status   AS ENUM ('scheduled', 'out_for_delivery', 'delivered', 'failed');
CREATE TYPE listing_status    AS ENUM ('acquired', 'refurbishing', 'listed', 'reserved', 'sold', 'returned');
CREATE TYPE resolved_by_kind  AS ENUM ('agent', 'copilot_auto');
CREATE TYPE msg_direction     AS ENUM ('inbound', 'outbound');
CREATE TYPE msg_channel       AS ENUM ('whatsapp', 'email', 'call');
CREATE TYPE msg_author        AS ENUM ('customer', 'agent', 'copilot_auto');
CREATE TYPE actor_role        AS ENUM ('l1_agent', 'supervisor', 'copilot_readonly');
CREATE TYPE audit_result      AS ENUM ('executed', 'pending_approval', 'rejected', 'replayed_noop');

-- ---------------------------------------------------------------------------
-- Actors
-- ---------------------------------------------------------------------------

CREATE TABLE app_actor (
  id          TEXT PRIMARY KEY,
  name        TEXT        NOT NULL,
  role        actor_role  NOT NULL,
  city_code   TEXT        NOT NULL,
  region      TEXT        NOT NULL
);
COMMENT ON COLUMN app_actor.name IS 'pii:direct_identifier';

-- ---------------------------------------------------------------------------
-- Core entities
-- ---------------------------------------------------------------------------

CREATE TABLE customer (
  id          TEXT PRIMARY KEY,
  name        TEXT NOT NULL,
  phone       TEXT NOT NULL,
  city_code   TEXT NOT NULL,
  region      TEXT NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON COLUMN customer.name  IS 'pii:direct_identifier';
COMMENT ON COLUMN customer.phone IS 'pii:direct_identifier';
COMMENT ON COLUMN customer.city_code IS 'pii:operational';

CREATE TABLE vehicle (
  id              TEXT PRIMARY KEY,
  reg_no          TEXT NOT NULL UNIQUE,
  make            TEXT NOT NULL,
  model           TEXT NOT NULL,
  year            INT  NOT NULL,
  km              INT  NOT NULL,
  listing_status  listing_status NOT NULL,
  city_code       TEXT NOT NULL,
  region          TEXT NOT NULL
);
-- reg_no identifies a person once combined with a city and a date, so it is a
-- quasi-identifier rather than operational. docs/INVARIANTS.md §H.
COMMENT ON COLUMN vehicle.reg_no IS 'pii:quasi_identifier';

-- "order" is reserved; the table is `orders` and the domain term stays "order".
CREATE TABLE orders (
  id          BIGINT PRIMARY KEY,
  customer_id TEXT NOT NULL REFERENCES customer(id),
  vehicle_id  TEXT NOT NULL REFERENCES vehicle(id),
  -- A materialised convenience. order_event is the source of truth; when the
  -- two disagree that is state_ledger_mismatch. docs/DOMAIN_v2.md §1.
  state       order_state NOT NULL,
  amount      NUMERIC(12,2) NOT NULL,
  city_code   TEXT NOT NULL,
  region      TEXT NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL,
  updated_at  TIMESTAMPTZ NOT NULL
);
CREATE INDEX ON orders (state);
CREATE INDEX ON orders (customer_id);
CREATE INDEX ON orders (vehicle_id);

-- Append-only. The ledger.
CREATE TABLE order_event (
  id          BIGSERIAL PRIMARY KEY,
  order_id    BIGINT NOT NULL REFERENCES orders(id),
  from_state  order_state,
  to_state    order_state NOT NULL,
  actor       TEXT NOT NULL,
  reason      TEXT,
  at          TIMESTAMPTZ NOT NULL,
  city_code   TEXT NOT NULL,
  region      TEXT NOT NULL
);
CREATE INDEX ON order_event (order_id, at);

CREATE TABLE payment (
  id           TEXT PRIMARY KEY,
  order_id     BIGINT NOT NULL REFERENCES orders(id),
  kind         payment_kind   NOT NULL,
  amount       NUMERIC(12,2)  NOT NULL,
  status       payment_status NOT NULL,
  txn_id       TEXT,
  captured_at  TIMESTAMPTZ,
  city_code    TEXT NOT NULL,
  region       TEXT NOT NULL
);
-- Amounts pass to the model (policy thresholds need them); txn references do not.
COMMENT ON COLUMN payment.amount IS 'pii:financial_passable';
COMMENT ON COLUMN payment.txn_id IS 'pii:financial_restricted';
CREATE INDEX ON payment (order_id);

CREATE TABLE refund (
  id               TEXT PRIMARY KEY,
  order_id         BIGINT NOT NULL REFERENCES orders(id),
  payment_id       TEXT   NOT NULL REFERENCES payment(id),
  amount           NUMERIC(12,2) NOT NULL,
  status           refund_status NOT NULL,
  -- Deterministic key. Replay must have no second effect. D2.
  idempotency_key  TEXT NOT NULL UNIQUE,
  created_at       TIMESTAMPTZ NOT NULL,
  city_code        TEXT NOT NULL,
  region           TEXT NOT NULL
);
CREATE INDEX ON refund (payment_id);

CREATE TABLE rc_case (
  id              TEXT PRIMARY KEY,
  order_id        BIGINT NOT NULL REFERENCES orders(id),
  vehicle_id      TEXT   NOT NULL REFERENCES vehicle(id),
  status          rc_status NOT NULL,
  -- Written by an external RTO system. Untrusted at prompt assembly. J5.
  blocked_reason  TEXT,
  rto_office      TEXT,
  opened_at       TIMESTAMPTZ NOT NULL,
  city_code       TEXT NOT NULL,
  region          TEXT NOT NULL
);
COMMENT ON COLUMN rc_case.blocked_reason IS 'trust:untrusted;pii:operational';
CREATE INDEX ON rc_case (order_id);

-- Scoped to the vehicle, not the order — so it can block a sale already paid for.
CREATE TABLE refurb_job (
  id              TEXT PRIMARY KEY,
  vehicle_id      TEXT NOT NULL REFERENCES vehicle(id),
  status          refurb_status NOT NULL,
  blocked_reason  TEXT,
  promised_at     TIMESTAMPTZ,
  completed_at    TIMESTAMPTZ,
  city_code       TEXT NOT NULL,
  region          TEXT NOT NULL
);
COMMENT ON COLUMN refurb_job.blocked_reason IS 'trust:untrusted;pii:operational';

CREATE TABLE delivery (
  id             TEXT PRIMARY KEY,
  order_id       BIGINT NOT NULL REFERENCES orders(id),
  slot_at        TIMESTAMPTZ,
  status         delivery_status NOT NULL,
  attempt_count  SMALLINT NOT NULL DEFAULT 0,
  courier_ref    TEXT,
  city_code      TEXT NOT NULL,
  region         TEXT NOT NULL
);
COMMENT ON COLUMN delivery.courier_ref IS 'trust:untrusted;pii:operational';
CREATE INDEX ON delivery (order_id);

-- ---------------------------------------------------------------------------
-- Tickets — the unit of work
-- ---------------------------------------------------------------------------

CREATE TABLE ticket (
  id                   TEXT PRIMARY KEY,
  -- Nullable on purpose: "my Swift hasn't arrived" arrives with no order number.
  order_id             BIGINT REFERENCES orders(id),
  customer_id          TEXT NOT NULL REFERENCES customer(id),
  channel              msg_channel NOT NULL,
  subject              TEXT NOT NULL,
  -- Denormalised copy of the first inbound message, for the queue list.
  -- Written by someone outside the company. Adversarial everywhere it appears.
  body                 TEXT NOT NULL,
  state                ticket_state NOT NULL,
  priority             ticket_priority NOT NULL,
  assigned_to          TEXT REFERENCES app_actor(id),
  reopen_count         SMALLINT NOT NULL DEFAULT 0,
  city_code            TEXT NOT NULL,
  region               TEXT NOT NULL,
  created_at           TIMESTAMPTZ NOT NULL,
  first_response_at    TIMESTAMPTZ,
  resolved_at          TIMESTAMPTZ,
  resolution_code      TEXT,
  resolved_by          resolved_by_kind,
  resolution_evidence  JSONB,
  -- Resolution without evidence is itself a detectable defect
  -- (ticket_resolved_without_cause), so the constraint states the intent while
  -- the rule catches historical rows.
  CONSTRAINT resolution_needs_provenance CHECK (
    state NOT IN ('RESOLVED', 'CLOSED')
    OR (resolution_code IS NOT NULL AND resolved_by IS NOT NULL)
  )
);
COMMENT ON COLUMN ticket.subject IS 'trust:untrusted;pii:free_text';
COMMENT ON COLUMN ticket.body    IS 'trust:untrusted;pii:free_text';
CREATE INDEX ON ticket (state);
CREATE INDEX ON ticket (assigned_to);
CREATE INDEX ON ticket (order_id);

-- Addition to DOMAIN_v2.md §1. See the header note.
CREATE TABLE ticket_message (
  id                TEXT PRIMARY KEY,
  ticket_id         TEXT NOT NULL REFERENCES ticket(id) ON DELETE CASCADE,
  direction         msg_direction NOT NULL,
  channel           msg_channel   NOT NULL,
  author            msg_author    NOT NULL,
  body              TEXT NOT NULL,
  -- Flagged, counted, surfaced — never silently stripped. J10.
  injection_flagged BOOLEAN NOT NULL DEFAULT false,
  at                TIMESTAMPTZ NOT NULL,
  city_code         TEXT NOT NULL,
  region            TEXT NOT NULL
);
-- Every inbound message is independently untrusted. Marking the field rather
-- than the request is what closes second-order injection. J5.
COMMENT ON COLUMN ticket_message.body IS 'trust:untrusted;pii:free_text';
CREATE INDEX ON ticket_message (ticket_id, at);

-- ---------------------------------------------------------------------------
-- Audit and conversation
-- ---------------------------------------------------------------------------

-- Append-only. No UPDATE or DELETE grant is issued in 02_rls.sql. A4.
CREATE TABLE action_audit (
  id               TEXT PRIMARY KEY,
  answer_id        TEXT NOT NULL,
  order_id         BIGINT REFERENCES orders(id),
  ticket_id        TEXT   REFERENCES ticket(id),
  action           TEXT NOT NULL,
  proposal         TEXT NOT NULL,
  proposed_by      TEXT NOT NULL REFERENCES app_actor(id),
  approved_by      TEXT REFERENCES app_actor(id),
  rule_id          TEXT NOT NULL,
  rule_version     INT  NOT NULL,
  idempotency_key  TEXT NOT NULL,
  executed_at      TIMESTAMPTZ,
  result           audit_result NOT NULL,
  city_code        TEXT NOT NULL,
  region           TEXT NOT NULL
);
-- The same key twice executes once. The second call is recorded as a no-op,
-- which is why this is not a UNIQUE constraint on the key alone.
CREATE INDEX ON action_audit (idempotency_key);
CREATE INDEX ON action_audit (answer_id);

-- A conversation is the thread; ticket_id on it is optional. A console-level
-- question ("how many deliveries missed SLA last week?") is not about any one
-- ticket, so it cannot hang directly off ticket like a turn used to. And a
-- fresh session on the same ticket must not require deleting history — it
-- opens a new conversation row and closes the old one instead.
CREATE TABLE conversation (
  id          TEXT PRIMARY KEY,                                   -- 'conv_<hex>'
  ticket_id   TEXT REFERENCES ticket(id) ON DELETE CASCADE,       -- NULL = console-level
  actor_id    TEXT NOT NULL REFERENCES app_actor(id),
  started_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  closed_at   TIMESTAMPTZ,                                        -- set when a new session starts
  city_code   TEXT NOT NULL,
  region      TEXT NOT NULL
);
-- "the open conversation for this ticket" / "the open console conversation
-- for this actor" are both lookups for the single live thread, hence partial
-- indexes on closed_at IS NULL rather than a full index on the FK alone.
CREATE INDEX ON conversation (ticket_id) WHERE closed_at IS NULL;
CREATE INDEX ON conversation (actor_id) WHERE closed_at IS NULL;

-- docs/DESIGN.md §7. Keyed to the conversation, not the ticket directly — a
-- conversation may itself be console-level (no ticket) or may be superseded
-- by a fresh session on the same ticket without losing prior turns.
--
-- Four memory components, each bounded independently. The distinction that
-- matters: everything here is carried so a later turn can REFER to it. Nothing
-- here is ever SERVED as an answer — every turn recomputes against live state.
CREATE TABLE conversation_turn (
  id              BIGSERIAL PRIMARY KEY,
  conversation_id TEXT NOT NULL REFERENCES conversation(id) ON DELETE CASCADE,
  -- Denormalised from conversation.ticket_id so the RLS policy shape and the
  -- existing (ticket_id, turn_index DESC) access pattern still work directly
  -- off this table. Nullable because the owning conversation may be console-level.
  ticket_id     TEXT REFERENCES ticket(id) ON DELETE CASCADE,
  turn_index    INT  NOT NULL,
  actor_id      TEXT NOT NULL REFERENCES app_actor(id),

  -- (1) BOUNDED RECENT TURNS. The operator's own words, for intent continuity
  -- ("shorter", "same for #3310"). Only the last N are ever read back.
  operator_text TEXT NOT NULL,

  -- (2) STRUCTURED CONVERSATION IR. The plan, not the prose. Closed schema, so
  -- it cannot grow. "It" resolves against this, never against the last answer's
  -- text — otherwise determinism (C1) is gone.
  ir            JSONB NOT NULL,

  -- (3) RESOLVED ENTITY IDS. Stable handles for what the turn was about, so
  -- "that order" and "the second one" resolve without re-running resolution.
  -- Ids only — never names, never PII.
  resolved_entities JSONB NOT NULL DEFAULT '[]'::jsonb,

  -- (4) PREVIOUS RESULT DIGEST. A fingerprint of what the last turn returned:
  -- which rules fired, which records were cited, and a hash of the state they
  -- were computed from. NOT the violations themselves.
  --
  -- Two jobs. It lets a later turn refer to a prior result ("who else is
  -- affected"), and on recompute the new hash is compared against it, so a
  -- changed answer can be reported AS a change rather than silently differing.
  --   { rule_ids: [], cited: [], state_hash: "...", answer_id: "..." }
  result_digest JSONB NOT NULL DEFAULT '{}'::jsonb,

  answer_id     TEXT,

  -- DISPLAY ONLY. The rendered answer, kept so a reloaded page can show the
  -- thread the operator already saw.
  --
  -- This is NOT a fifth memory component and is never read back into a prompt.
  -- The memory path (app/agent/conversation.py `load`) selects specific columns
  -- and this is deliberately not among them. Storing prose is fine; re-sending
  -- it to the model is what ADR-010 forbids, because that makes a hallucination
  -- an input to the next turn.
  rendered_answer JSONB,

  at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  city_code     TEXT NOT NULL,
  region        TEXT NOT NULL,
  UNIQUE (conversation_id, turn_index)
);
COMMENT ON COLUMN conversation_turn.operator_text IS 'trust:untrusted;pii:free_text';
CREATE INDEX ON conversation_turn (conversation_id, turn_index DESC);
