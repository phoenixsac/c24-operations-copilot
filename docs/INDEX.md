# Docs Index

Design docs for the AI Operations Copilot (Cars24-style used-car ops console).

The schema, RLS, seed, FastAPI service (including the 15-rule engine), the
agentic layer (router, planner, resolver, synthesiser, conversation store,
write path, cohorts, policy engine) and the model boundary (Sarvam adapter,
fake adapter, gateway, redaction) are built and exercised by the eval suite —
**all 55 fixture cases pass, and all 15 rules are covered**.

Green is against the fake adapter: deterministic, offline, free. That is the
claim worth making, because it means every assertion holds against
deterministic execution and a live failure is a provider problem rather than a
logic one.

What is not built is named in `DESIGN.md` §12 — the answer-replay endpoint
(API-12) and the invariants deferred in `SCOPE.md` §2. See `IMPL.md` for
row-by-row status.

| Doc | What it is |
|---|---|
| [README_v3.md](README_v3.md) | The submission-level overview: position, usage model, autonomy tiers, entities, auth, storage, assumptions, rules, evals, query shapes, API, console, principles |
| [DOMAIN_v2.md](DOMAIN_v2.md) | Data model only: 11 tables + audit log, order state machine, ticket lifecycle, invariant→rule table, scoping, RLS, seed plan |
| [INVARIANTS.md](INVARIANTS.md) | The falsifiable requirement list (A–J, I). Each invariant paired with how it's verified |
| [DESIGN.md](DESIGN.md) | The backend design. Layered architecture and model boundary (§1), request + write + injection flows and the seven query shapes (§2), stack decisions incl. FastAPI and LangGraph (§3), component specs for router/planner/synthesiser/conversation/redaction (§4), implementation map (§5), the IR (§6), conversation state (§7), storage sketch (§9), build order (§10), **indexed decision records, ADR-001 … ADR-040 (§11)**, build status (§12) |
| [SCOPE.md](SCOPE.md) | 5-day build triage: build / stub / skip, quantity trims, day plan, decision rule |
| [STITCH_PROMPTS.md](STITCH_PROMPTS.md) | Google Stitch prompts for the 5 UI screens |
| [DATA_MODEL.md](DATA_MODEL.md) | Diagrams: ERD, both state machines, rule→entity map, RLS flow, trust boundaries, PII classes |
| [GLOSSARY.md](GLOSSARY.md) | Every term in the UI and what backs it in the data model |
| [questions_v2.json](questions_v2.json) | Eval fixture — 55 cases, asserts on structured IR not prose |

Outside `docs/`: [`../README.md`](../README.md) is the entry point, `../db/init/`
holds the schema/RLS/seed, `../ui/` is the console.

## One-paragraph summary

Backend service where the **LLM is a query planner and a phrasing layer, nothing else**. `NL query → router → deterministic execution → structured result → LLM phrases it → answer + evidence`. Causes come from a versioned rules engine computing a state diff (expected vs observed), never from the model. Trust boundaries live in Postgres RLS, not in prompts. Writes are proposed → human-approved → idempotent → audited. Refusal is a tested outcome.

## Reading order

1. `README_v3.md` — full picture
2. `INVARIANTS.md` — what must be true and how it's proven
3. `DESIGN.md` — how components satisfy those invariants
4. `SCOPE.md` — what actually gets built in 5 days
5. `questions_v2.json` — what gets graded

## Resolved conflicts

The documents were at different versions. All eight disagreements are now
settled; the decision is recorded in the doc that lost, rather than deleted, so
the reasoning stays visible.

| # | Conflict | Decision |
|---|---|---|
| 1 | Rule count: 15 (README/DOMAIN) vs 8 (SCOPE §4) | **15.** SCOPE's trim rejected — it would have left `D-02`, `D-04`, `T-03`, `T-05` permanently red and dropped the only cross-seam rule. All 15 seeded. |
| 2 | Seed size: 60 vs 35 | **65** (grew from the 60 first agreed here). 42 healthy, 21 broken, 2 unanswerable, plus 1 injection ticket and 4 further injection surfaces for X-02b/c/d/h. Asserted on boot. |
| 3 | Eval tiering: ~20 gating vs all | **All 52 gate** (grew from 49 as D-07, T-06, K-01 were added). 27 core, 16 hard, 7 medium, 2 trivial. No `stretch` tier; `difficulty` is a label, not a gate. |
| 4 | Query console: build or skip | **Build.** Records stays the real fallback (F4); the console ships as a supervisor tool. |
| 5 | Fixture filename | **`questions_v2.json`.** No `questions.json` ever existed; two doc references were stale. |
| 6 | Table count: 11 vs 12 | **12** domain tables — 11 entities plus the audit log, including `ticket_message`. `app_actor` was infrastructure and not counted. Since settled, the conversation store added two more physical tables (`conversation`, `conversation_turn`), so the schema now has **15 tables total**; the 12-vs-11 argument itself is unaffected, it was never about those two. |
| 7 | Seed count in the implementation | Folded into #2. |
| 8 | `tenant_id` in STITCH screen 5 | **Removed.** There is no tenant; the scoping keys are `city_code` and `region`. |

## Still to write

- `GET /audit/{answer_id}` — replaying a past answer (API-12, invariant A2).
- The four knowingly deferred invariants: F5 backpressure, F6 concurrency,
  H11 retention, I3 reversible migrations (`SCOPE.md` §2).

The three items once listed here — `DESIGN.md`'s open decisions, an
invariant-by-invariant build table, and a generated PII field-classification
table — are now covered: open decisions close as ADRs in `DESIGN.md` §11,
build status lives in `DESIGN.md` §12, and PII classes are carried as column
comments in `01_schema.sql` and summarised in `DATA_MODEL.md` §7.
