# Scope Decisions — What to Build, Stub, and Skip

A 5-day build. `INVARIANTS.md` and `DESIGN.md` describe a complete design; this file says which parts get code.

**The framing:** the design documents stay complete. `DESIGN.md` §10 then states which invariants are implemented, which are stubbed, and which are deliberately deferred with reasons. Over-engineering is building the cache. It is not having thought about caching.

Reach for this file whenever the build is running behind and something has to give.

---

## 1. Build — these are the signal

Cut anything else before these. They're what separate this from a chat wrapper, and most are cheap.

| Item | Invariants | Why it's non-negotiable |
|---|---|---|
| Schema, migrations, RLS policies | E3, H10 | The central claim of the design. Without the isolation test it's an assertion. |
| RLS isolation test | E3 | Three lines. Proves the claim at the database, not the repository. |
| Deterministic seed script | C7 | Every eval case depends on it. Also the demo. |
| Rules engine | B3, I1, I2 | The thing that makes diagnosis auditable instead of generated. |
| IR schema | C1, J1, J6 | Most invariants hold because of its shape, not a runtime check. |
| Typed tool layer + timeouts | E1, E2, F1 | Cheap, and F3 partial-failure depends on it. |
| Fake model adapter | C6 | Build early. Without it the eval suite is slow and non-deterministic. |
| Eval harness | C3, C4, C5 | Built at step 5 it constrains the design; built last it's a report. |
| Propose / approve / idempotency | D1, D2, D3 | The single most demonstrable safety property. |
| Append-only audit log | A4, A6 | One table, one missing grant. |
| Redaction at prompt boundary | H2, H3 | The golden test is one assertion with permanent value. |
| Injection structural property | J1, J2 | Free if the IR is right. Expensive to retrofit. |
| Multi-turn conversation | §5 | Half a day. Without it the demo reads as a search box. |

---

## 2. Stub — design it, state it, don't build it

Write the interface or the config, note it in `DESIGN.md`, move on.

| Item | Invariant | Why stub | What "stubbed" means |
|---|---|---|---|
| Backpressure / rate limiting | F5 | Needs traffic to be meaningful | Retry with backoff in the gateway; note the design |
| Second provider adapter | F7 | The interface is the point | The fake *is* the second implementation |
| Concurrency control | F6 | Single-user demo | Note optimistic versioning as the intended approach |
| Retention policy | H11 | Nothing to expire in 5 days | A config value and one sentence |
| Reversible migrations | I3 | Up-only is fine at this size | Note that down migrations would ship in production |
| Feedback → eval case | I4 | Nice, not load-bearing | An endpoint that writes a candidate fixture, unused |
| Prompt version replay | A5 | Only one version will exist | Store the version; don't build cross-version replay |
| Trace retention separation | — | Same Postgres is fine | Different table, same database |

---

## 3. Skip — actively don't build

These cost time and buy nothing at demo scale. Say so explicitly rather than leaving them looking forgotten.

| Item | Invariant | Why skip |
|---|---|---|
| Semantic cache | G5 | Zero hits with no load. Pure cost. Note the cache key design in `DESIGN.md` instead. |
| MCP transport for tools | E1 | In-process satisfies E1/E2 identically with far fewer moving parts. Revisit only if MCP is itself a talking point. |
| Trained classifier router | — | A model-based router with one prompt is enough. Classifier is a day of work for latency nobody is measuring. |
| ~~Query console (UI screen 5)~~ | E7 | **REJECTED — built.** The Records view is still the real fallback, but the console ships. |
| Mobile UI | — | Ops agents work on desktop. State it as a scope decision. |
| Real auth (OIDC etc.) | D4 | Stub the session with a header-supplied actor. The *delegation model* is the point, not the login page. |
| Streaming responses | — | Nice UX, zero architectural signal. |
| Sell-side funnel | — | Already scoped out. Two stub states only. |

---

## 4. Trim the ambitious bits

Places where the design is right but the quantity is wrong.

**Rules: 15 → 8.** ~~Eight covers every distinct *class* of failure.~~

> **REJECTED.** All 15 rules ship. The trim would have left four eval cases
> permanently red (`D-02`, `D-04`, `T-03`, `T-05`) and dropped the only
> cross-seam case (`seller_payout_hold`) and the whole ticket-rule family. All
> 15 are seeded and verified in `db/init/03_seed.sql`.

**Evals: tier the fixture.** ~~Mark ~20 as `core` and the rest as `stretch`.~~

> **REJECTED.** All 49 cases are in scope and all of them gate: 24 `core`,
> 16 `hard`, 7 `medium`, 2 `trivial`. No `stretch` tier. The existing
> `difficulty` field stays as a label, not as a gate.
>
> *Since:* **55 cases.** Three were added because the coverage check found
> rules with data but no case asserting on them, or a shape with none; three
> more because an audit found behaviour no case looked at — a proposal that
> could not be approved, token counts that grew forever, a planner decision
> nobody could audit.
>
> A tier that does not gate is a tier that rots; a rule with no case is a rule
> nobody has checked; and a green suite is a statement about the cases in it
> and nothing more.

**Seed: 60 → 35 orders.** ~~Enough for aggregates to be non-trivial.~~

> **REJECTED.** 60 orders, as originally specified: 40 healthy, 18 broken
> (at least one clean instance per rule, 3 firing two at once), 2 unanswerable,
> 1 injection ticket. Built and asserted on boot.
>
> *Since:* **65 orders (42 healthy, 21 broken, 2 unanswerable), 26 tickets.**
> Grew as eval cases named orders the seed did not contain — the fixture is the
> contract, so the data moved to meet it.
>
> The boot checks made each gap visible, but note what they are: `RAISE
> WARNING`, not `RAISE EXCEPTION`. A seed with the wrong counts **still boots**,
> and the warning scrolls past in the container log. That is weaker than
> "asserted" implies and is recorded as a gap rather than rephrased away.

**Tier 2: keep, but first to go.** The gate is roughly 40 lines and it's the most distinctive idea in the design. If day 4 goes badly, cut it and describe it in `DESIGN.md` — the tier framing survives without the implementation.

> *Kept.* Built and passing (`AU-01`, `AU-02`, `AU-04`, `X-02f`). It also lost
> its confidence threshold along the way — see DESIGN.md ADR-026. A number the
> model writes about its own output is not evidence.

---

## 5. Day plan

| Day | Work | Done when |
|---|---|---|
| 1 | Schema, RLS, isolation test, seed script | Raw SQL on a scoped connection returns zero foreign rows |
| 2 | Rules engine, tool layer, fakes | Rules pass against fixtures with no I/O |
| 3 | Eval harness, router, planner, IR | Core tier runs end to end with zero provider calls |
| 4 | Synthesiser, redaction, propose/approve, multi-turn | A ticket can be worked start to finish |
| 5 | Tier 2 if it fits, README, DESIGN.md, video | Documentation done |

**Day 5 is documentation, not code.** That's the day the submission is actually won. If code slips into day 5, cut from §4 rather than from the docs.

---

## 6. Decision rule

When something has to give, in order:

1. Cut quantity before capability — fewer rules, fewer eval cases, fewer seed rows.
2. Cut breadth before depth — one shape done properly beats seven done thinly.
3. Cut features before invariants — losing Tier 2 is fine; losing the audit log is not.
4. Never cut the eval harness or the seed script. Everything else is verified through them.
5. Anything cut goes in `DESIGN.md` with a reason. An invariant listed and knowingly deferred reads as judgment; one quietly unmet reads as an oversight.
