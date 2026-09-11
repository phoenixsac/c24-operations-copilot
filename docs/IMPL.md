# Implementation Tracker

Checkpoint list for the build. One line per unit of work, with a stable ID so it
can be referenced directly ("do CORE-4").

**Legend:** ✅ done · 🟡 partial · ⬜ not started · ⛔ blocked

**Spec references:** invariant IDs (`D2`, `J7`) → `INVARIANTS.md` · §N → `DESIGN.md`

| Layer | Done | Total |
|---|---|---|
| INF · Infrastructure | 5 | 5 |
| DB · Data layer | 8 | 8 |
| API · Transport | 13 | 13 |
| CORE · Deterministic core | 10 | 10 |
| AGT · Agentic | 7 | 7 |
| MDL · Model boundary | 5 | 8 |
| EVAL · Eval harness | 7 | 7 |
| UI · Console | 11 | 11 |
| OBS · Trace & budgets | 1 | 5 |
| **Total** | **71** | **73** |

---

## 0 · INF — Infrastructure

| ID | Item | Status | Where |
|---|---|---|---|
| INF-1 | `docker compose` — db + api + ui | ✅ | `docker-compose.yml` |
| INF-2 | Postgres 16 container, seeded on first boot | ✅ | `db/init/` |
| INF-3 | FastAPI service container | ✅ | `api/Dockerfile` |
| INF-4 | Vite dev container, proxy `/api` → api | ✅ | `ui/Dockerfile` |
| INF-5 | Configurable host ports (`POSTGRES_PORT`, `API_PORT`, `UI_PORT`) | ✅ | `docker-compose.yml` |

---

## 1 · DB — Data layer

| ID | Item | Status | Inv. |
|---|---|---|---|
| DB-1 | Schema: 11 entities + `action_audit` (12 tables) + conversation pair | ✅ | — |
| DB-2 | `ticket_message` — thread, per-message untrusted flag | ✅ | J5 |
| DB-3 | `conversation` + `conversation_turn` — 4 memory components | ✅ | §7 |
| DB-4 | Three roles: `app_user`, `app_readonly`, `app_migrator` | ✅ | E7 |
| DB-5 | RLS policies + `FORCE` on 13 scoped tables | ✅ | E3, H10 |
| DB-6 | `assert_rls_isolation()` — 3 checks, all 0 | ✅ | E3 |
| DB-7 | Append-only: no UPDATE/DELETE grant on audit + ledger | ✅ | A4 |
| DB-8 | Deterministic seed — 65 orders, all 15 rules, asserts on boot | ✅ | C7 |

---

## 2 · API — Transport

| ID | Item | Status | Inv. |
|---|---|---|---|
| API-1 | `with_session` — txn + `SET LOCAL` scope, sole DB path | ✅ | E3 |
| API-2 | Session from actor row; never from request | ✅ | D4, E3 |
| API-3 | `GET /tickets` — RLS-scoped queue + stats | ✅ | — |
| API-4 | `GET /tickets/{id}` · `/records` — 404 on out-of-scope | ✅ | F4 |
| API-5 | `GET /cohorts` · `/cohorts/tickets` — all 15 rules | ✅ | — |
| API-6 | `GET /audit` — append-only view | ✅ | A6 |
| API-7 | `POST /ask` — the only NL surface | ✅ | — |
| API-8 | `POST /tickets/{id}/assign` — assignee is the caller | ✅ | — |
| API-9 | `POST /tickets/{id}/resolve` — code + evidence required | ✅ | A6 |
| API-10 | `POST /actions/{id}/approve` — idempotent, replay → no-op | ✅ | D1, D2 |
| API-11 | `POST /query` — supervisor only, SELECT-only, 5s, 500 rows | ✅ | E7 |
| API-12 | `GET /audit/{answer_id}` — replay a past answer | ⬜ | A2 |
| API-13 | `GET /conversations` · `/list` · `POST /conversations/new` | ✅ | §7 |

**API-10:** replay path works; first-execute path is a stub — no proposal store,
so approve returns `no_matching_proposal`. Needs AGT-6.

---

## 3 · CORE — Deterministic core (no I/O, no model)

| ID | Item | Status | Inv. |
|---|---|---|---|
| CORE-1 | Rules engine — 15 rules, versioned, pure | ✅ | B3, I1, I2 |
| CORE-2 | Causal ranking — cause outranks symptom (`depth`) | ✅ | B3 |
| CORE-3 | `expected_state()` — derived from ledgers | ✅ | B3 |
| CORE-4 | `CONFIG` — thresholds as data | ✅ | I6 |
| CORE-9 | `app/clock.py` — one clock, pinned to the seed | ✅ | C7 |
| CORE-10 | Glossary — 48 curated terms, coverage asserted vs enums | ✅ | B1 |
| CORE-5 | Authorization gate — re-checked at execute vs approver | ✅ | D3 |
| CORE-6 | Policy engine — eligibility vs config, shows its work | ⬜ | I6 |
| CORE-7 | Cohort/aggregate filter — derived, not model-authored | ✅ | J6 |
| CORE-8 | Proposal store + deterministic idempotency key | ✅ | D2 |

**CORE-5:** gate logic exists inline in `ask.py`; not extracted, not re-checked
at execute. **CORE-8:** key derivation is done; proposals aren't persisted.

---

## 4 · AGT — Agentic layer

| ID | Item | Status | Inv. |
|---|---|---|---|
| AGT-1 | Router — model call + keyword fallback, operator turn only | ✅ | J7 |
| AGT-2 | Router confidence floor → `unsupported` → refusal | ✅ | B2 |
| AGT-3 | Planner — NL → validated IR, one repair retry | ✅ | J1, J6 |
| AGT-4 | Entity resolution — order or ticket → RLS-scoped snapshot | ✅ | — |
| AGT-5 | Synthesiser — facts → prose, checked before it ships | ✅ | B1, J9 |
| AGT-6 | Action proposal → approve → execute → audit | ✅ | D1, D2, D3, D6 |
| AGT-7 | Conversation store — 4 components, persisted, RLS-scoped | ✅ | §7, C1 |

Files: `api/app/agent/{planner,resolve,synthesise,tier2}.py`.

**AGT-1** calls the model and falls back to keywords on any failure — same
function signature, so the fallback is a path rather than an error branch.
**AGT-5** checks its own output against the fact set and reverts to the template
on an unsupported token; the fake adapter's synthetic replies are rejected by
this guard on every run, which is how we know it works.
**AGT-7** persists all four memory components to `conversation_turn` inside the
same RLS-scoped transaction as everything else — verified: a Bengaluru agent
reads 0 turns of a Mumbai thread. `/ask` accepts no history from the client,
because a client that could supply its own conversation could also fabricate
one, and "the previous turn resolved order 4110" is exactly the sentence that
walks an agent into another city's data.

**No model prose is stored or re-sent.** Verified by querying for it: 0 rows.
"Make it shorter" carries a *style constraint*, not the previous draft, so a
redrafted reply is regenerated from records rather than degraded from a copy.

`state_hash` covers rule-relevant fields only — resolving the RC case moved it
`6ad583a2…` → `1a7fcc4d…` and the answer recomputed to zero rules. Hashing the
whole snapshot would fire on every unrelated write, and a drift signal that
fires constantly is one nobody reads. This closes the open gap in §11.

---

## 5 · MDL — Model boundary

**Provider: Sarvam AI 105B.** See § Provider notes below.

| ID | Item | Status | Inv. |
|---|---|---|---|
| MDL-1 | Adapter interface — provider not structurally required | ✅ | F7 |
| MDL-2 | Sarvam adapter — live, verified | ✅ | — |
| MDL-3 | Fake adapter — fixture replies, no network. **Default** | ✅ | C6 |
| MDL-4 | Gateway — retries, budgets, redaction gate | 🟡 | A3, A5 |
| MDL-5 | Untrusted-content wrapping at prompt assembly | 🟡 | J4 |
| MDL-6 | Token accounting + cost per request | ⬜ | G3 |
| MDL-7 | Retry + backpressure | ⬜ | F5 |
| MDL-8 | Redaction — 5 layers, fails closed | ✅ | H2–H6 |

**MDL-4** does retries, token accounting (including reasoning tokens, broken out
separately) and the fail-closed redaction gate. Prompt versioning (A5) is
emitted in the trace but not stored per answer.

Files: `api/app/model/{base,sarvam,fake,gateway,config}.py`. Config in `.env`
(`.env.example` is committed, `.env` is not). `MODEL_ADAPTER=fake` is the
default: a fresh clone with no key boots, serves the console, runs the evals.

### Redaction layers (MDL-8)

| # | Layer | Carries |
|---|---|---|
| 1 | Projection — PII columns never selected into a prompt | most of the weight |
| 2 | Pseudonymisation — `customer:c_8821`, mapping RLS-scoped | H3, H7 |
| 3 | Free-text scrub — `+91`, Aadhaar, PAN, IFSC, reg_no | H4 (weak on names) |
| 4 | Fail closed — drop, never send | H5 |
| 5 | Golden test — no prompt matches PII patterns | H2 |

---

## 6 · EVAL — Eval harness

Fixture: `questions_v2.json` — **52 cases, all gating.** Three added to close EVAL-7 coverage gaps (`delivery_attempts_exhausted`, `ticket_orphaned`) and the new `concept` shape.

| ID | Item | Status | Inv. |
|---|---|---|---|
| EVAL-1 | Runner — load fixture, execute, assert on IR | ✅ | C4 |
| EVAL-2 | Shape accuracy | ✅ | — |
| EVAL-3 | Rule accuracy — set match, `primary_rule` first | ✅ | B3 |
| EVAL-4 | Hallucination rate — `must_not_mention` + unsupported entities | ✅ | B1 |
| EVAL-5 | Refusal precision | ✅ | B2 |
| EVAL-6 | Determinism — paraphrases → identical IR (`same_ir_as`) | ✅ | C1, C2 |
| EVAL-7 | Coverage check — every rule_id in ≥1 case | ✅ | C3 |

Run: `cd api && .venv/bin/python -m evals.run --shape lookup [--live]`.
Default is the fake adapter (ADR-014); `--live` sets `MODEL_ADAPTER=sarvam`
explicitly, so a "live" run can never silently be a fake one.

**EVAL-7 currently fails on the fixture**, and correctly: `ticket_orphaned` and
`delivery_attempts_exhausted` are two of the 15 rules and no case exercises
either. Either the fixture gains cases or those rules are not actually
verified — recorded rather than suppressed.

### Fixture composition

| By shape | n | | By tier | n |
|---|---|---|---|---|
| lookup | 14 | | core | 24 |
| diagnosis | 12 | | hard | 16 |
| action | 8 | | medium | 7 |
| cohort | 4 | | trivial | 2 |
| aggregate | 3 | | | |
| policy | 3 | | refusals | 3 |
| query_console | 2 | | multi-turn | 4 |
| unshaped | 3 | | | |

---

## 7 · UI — Console

| ID | Item | Status |
|---|---|---|
| UI-1 | Queue — search, state filter, pagination, assign | ✅ |
| UI-2 | Scope chip — RLS boundary made visible | ✅ |
| UI-3 | Ticket workspace — three panes | ✅ |
| UI-4 | Answer card — 4 states (diagnosis/refusal/proposal/degraded) | ✅ |
| UI-5 | Evidence pane — Evidence / Records / Trace | ✅ |
| UI-6 | Records modal — F4 fallback, ledger timeline | ✅ |
| UI-7 | Approval modal — gate, idempotency key, "not executed" | ✅ |
| UI-8 | Cohorts — 10 order rules + 5 ticket rules | ✅ |
| UI-9 | Audit log — append-only, replay link | ✅ |
| UI-10 | Query console — supervisor-gated | ✅ |
| UI-11 | Thread hydration, session history, console chat, draft/provenance/tier2 | ✅ |

---

## 8 · OBS — Trace, budgets, autonomy

| ID | Item | Status | Inv. |
|---|---|---|---|
| OBS-1 | Trace store — per-stage timing, model, tokens | ⬜ | A3, G1 |
| OBS-2 | Budgets — tool calls, depth, wall-clock, tokens | 🟡 | D5 |
| OBS-3 | Per-conversation budget — 20-turn cap enforced, tokens pending | 🟡 | D5, §7 |
| OBS-4 | Metrics — rule fire rates, refusal rate, tool errors | ⬜ | I5 |
| OBS-5 | Tier 2 auto-reply gate — structured state only | ✅ | J8, D7 |

---

## 9 · Build order

Dependencies, not priorities. Each step is independently verifiable.

Steps 1–6 are done. The remaining order is by shape, one vertical slice at a
time — implement, run that shape's eval cases, fix, then move on. `lookup`
(14 cases) is complete; `diagnosis` is next.

| # | Step | Status |
|---|---|---|
| 1 | MDL-1 + MDL-3 (interface + fake adapter) | ✅ |
| 2 | EVAL-1…7 harness | ✅ |
| 3 | AGT-3 planner (first real model call) | ✅ |
| 4 | MDL-8 redaction — **had to precede AGT-5** | ✅ |
| 5 | AGT-5 synthesiser | ✅ |
| 6 | AGT-1 router as a model call, keywords kept as F4 fallback | ✅ |
| 7a | Shape slice: **diagnosis** (12 cases) | ✅ |
| 7b | Multi-turn (M-01…M-04) + conversation persistence | ✅ |
| 7c | Glossary + `concept` shape (7th) | ✅ |
| 7d | Shape slice: **action** (8 cases) + write path | ✅ |
| 7e | Shape slices: **cohort** (4) + **aggregate** (3) | ✅ |
| 7f | **Remaining: policy (3) → query_console (2)** | next |
| 8 | AGT-6 + CORE-8 + API-10/12 (write path, replay) | with `action` |
| 9 | CORE-7 filter AST → SQL | with `cohort`/`aggregate` |
| 10 | CORE-6 policy engine | with `policy` |
| 11 | AGT-7 conversation-store writes, UI-11 | — |
| 12 | OBS-1…4 | — |

**Step 1 before step 2 before step 3 is load-bearing.** Fake adapter first →
the suite is fast, free and deterministic. Fake adapter last → C1 and C5 quietly
stop being enforced.

---

## 10 · Provider notes — Sarvam AI 105B

Replaces the Anthropic assumption in `DESIGN.md` §1b. The adapter interface
(MDL-1) exists precisely so this is a swap, not a redesign — **F7 says no
provider is structurally required**, and this is the test of it.

Endpoint: `https://api.sarvam.ai/v1/chat/completions`, OpenAI-compatible.

### Verified against the live API, 2026-09-10

| # | Question | Answer | Consequence |
|---|---|---|---|
| 1 | Constrained JSON / schema output? | **Yes.** `response_format: {type: json_schema, strict: true}` returns well-formed JSON and respects `enum` | AGT-3 can rely on the shape. Without an `enum` it invents values — a bare `{shape: string}` schema returned `"order_status_inquiry"`, not one of our six |
| 2 | Tool/function calling? | `tool_calls` field present in the response envelope; not exercised | IR goes over `response_format`, not tools. Simpler, and one less thing to verify |
| 3 | Reasoning model? | **Yes, and this is the big one.** `content` is null while it thinks; thinking lands in `reasoning_content`. `max_tokens` budgets *both* | A 256-token cap returned 256 reasoning tokens and an empty answer, `finish_reason: "length"`, HTTP 200. Adapter enforces a 4096 floor and raises on empty content rather than passing `""` up as an answer |
| 4 | `reasoning_effort`? | `low` \| `medium` \| `high`. **No `none`** | Reasoning cannot be switched off. Measured 637–2579 reasoning tokens for a one-line classification; `low` was not reliably cheaper than `high` |
| 5 | Deterministic at `temperature: 0` + `seed`? | **No.** Two byte-identical requests returned `diagnosis` and `action` | C1/C2 cannot be delegated to the decoder. See below |
| 6 | Latency | ~8s for a schema-constrained classification | The 20s timeout in the first draft was too tight; raised to 60s |
| 7 | Self-hosted or API? | Hosted API | H10/H11 and the redaction argument stand as written in `INVARIANTS.md` §H |

### C1/C2 — determinism has to move

The provider does not give it. Same prompt, same temperature, same seed,
different shape. So determinism gets enforced **above** the model:

- **Cache the IR**, keyed on `(normalised_query, scope, schema_version)`. The
  same question asked twice reuses the first IR rather than re-rolling it.
- The **rules engine is already deterministic** — B3 means the model never picks
  the cause, so a wobbly shape classification changes which tool runs, not what
  is true. That bounds the damage.
- **Evals run against the fake adapter** (C6), which is deterministic by
  construction. C1/C2 stay assertable.
- `DESIGN.md` §11 needs a line saying determinism is a caching property here,
  not a decoding one. Silence would read as a claim.

### G4 is at risk

The invariant is *"model tier is matched to task — routing does not use the
synthesis model."* With a single 105B model serving router, planner and
synthesiser, that is unsatisfiable as written.

`reasoning_effort` is the only tier control the API exposes, and the measurement
above shows it does not reliably reduce spend — `low` burned 1508 completion
tokens where `high` burned 1021. So it does not rescue G4 either.

Two honest options — pick one and record it in `DESIGN.md` §11:

- **Restate G4** as "stage-appropriate decoding" — the trace still asserts
  per-stage config (effort, max tokens, prompt version), just not per-stage
  model.
- **Keep G4** and add a small second model for the router only. The router's
  output space is six values; almost anything serves, and it would also cut the
  ~8s/637-token floor that 105B charges for a one-word classification.

The second is the better trade on cost alone, independent of the invariant.
Either way, do not leave G4 stated and quietly unmet — `SCOPE.md` §6.5.

### Redaction gets no easier

Sarvam is a **hosted API**, not self-hosted. So the trust boundary is external
exactly as `INVARIANTS.md` §H assumes: everything placed in a prompt has left
the building, and H11 retention is the provider's policy, not ours. MDL-8 is
load-bearing and stays where it is in the build order — before the synthesiser,
which is the first stage that would otherwise want to see customer text.

`gateway.py` therefore **fails closed today**: a networked adapter refuses any
call not explicitly marked as having passed redaction. Nothing calls the gateway
on the request path yet, so this costs nothing now and cannot be forgotten later.

### One thing that gets harder

Indian-language ticket text is likelier with Sarvam in the loop. Two knock-ons:
**H4** — the regex scrubber is English/format-anchored and will miss
Devanagari-script PII; **J10** — injection detection degrades further across
scripts, which is survivable (J11) but the flag rate becomes less meaningful.

### Found by running the suite live, not by reading docs

| Symptom | Cause | Fix |
|---|---|---|
| Synthesiser silently produced nothing | ~3,300 reasoning tokens spent on a two-sentence paragraph, then `finish_reason: "length"`, empty content, **HTTP 200** | `max_tokens` 4096 → 8192 for that stage |
| Router emitted `{"shape": "lookup"` — no closing brace | Same budget exhaustion, cut mid-JSON rather than before it | 8192 for router and planner too |
| A clipped reply could parse into a valid-looking object with fields missing | The guard only caught total silence, not truncation | Adapter raises on `finish_reason == "length"` whether or not text came back |

### Diagnosis slice — what it needed beyond the read path

| Built | For |
|---|---|
| Registration-number resolution (`MH12AB1234` → vehicle → orders) | D-06 |
| `ticket → customer → orders`, with `Ambiguous` when several fit | T-04 |
| `app/data/faults.py` — typed source failure, so B5/F3 are testable at all | X-04 |
| Delegation guard: "…and do what it says" never reaches `action` | X-02 |
| Operator's own turn is scrubbed before any prompt | D-06 |

Per-case latency live is **26–133 s** — three model calls, each ~8 s of API time
plus reasoning. That is the strongest argument yet for a small router model
(`DESIGN.md` ADR-023): a 105B reasoning model is being paid to choose between
six labels.

Also correcting the note above: the redaction gate is no longer inert. `/ask`
now passes the gateway, so every live model call goes through MDL-8.

---

## 11 · Known gaps carried forward

| Gap | Where | Note |
|---|---|---|
| `DESIGN.md` §11 open decisions | 8 unresolved | MCP transport, cache key, ambiguity handling, Tier 2 placement, conversation reset, concurrency, trace store |
| Window sizes in §7 asserted, not derived | AGT-7 | `WINDOW = 3` is still a guess. Deriving it needs more multi-turn cases than the fixture's four |
| ~~`state_hash` undefined~~ | AGT-7 | **Closed.** Covers rule-relevant fields only; verified to move on a real state change and hold otherwise |
| F5, F6, H11, I3 | stated, deferred | Backpressure, concurrency, retention, reversible migrations — `SCOPE.md` §2 |
