# Glossary — what the words on screen mean

Terms an operator sees in the console, and what each one is grounded in. If a
term appears in the UI and not here, it is decoration and should be removed.

---

## The answer card

The structured block the copilot returns. Six parts, in this order, and the
order is the argument: verdict before evidence, cause before action.

| Term | What it is | Where it comes from |
|---|---|---|
| **Verdict** | One line: what is true and what is blocked. "Payment is fine. Delivery is blocked on RC transfer." | Phrased by the model from a structured result. The model never picks the cause. |
| **Diagnosis strip** | Three boxes — Expected, Observed, Stuck. | The state diff. Expected is computed from the ledgers; observed is `orders.state`. |
| **Rule chip** | `rc_transfer_stall v2`, red. Hover shows the field values that fired it. | The rules engine. Named and versioned so any answer can be replayed. |
| **Routing confidence** | A number, `0.91`, labelled "routing confidence" on the card. Thresholded, not decorative — below `ROUTER_CONFIDENCE_FLOOR` (0.35) the router emits `unsupported` and the turn refuses rather than guesses. | The router's own certainty in its shape classification. Emitted with every answer. |
| **Cited evidence** | Chips naming the exact records the answer rests on: `payment #P-9912`. | Only records actually retrieved. No claim appears without one. |
| **Propose action** | A button. Names an action from a fixed list. | The rules engine produced the list. The model selects; it cannot author one. |

**Provenance.** Under a cited-evidence chip, a collapsed disclosure — closed by
default, so the card stays readable, but one click away for an operator who
wants to audit it. Opens to a raw field-level line; it reads like a DB row on
purpose. This is what makes "cited evidence" a checkable claim rather than a
label: every value traces to the column it came from.

### Four states the card can be in

| State | Looks like | Means |
|---|---|---|
| **Diagnosis** | Full card, red rule chip, action button | Rules fired, cause identified |
| **Refusal** | Grey, italic, "Insufficient data" | No data supports an answer. This is a correct outcome, not an error. |
| **Proposal** | Amber gate, idempotency key, "not executed" | A write is proposed and waiting on a human |
| **Degraded** | Names the unavailable source | A dependency failed and is named, never treated as an empty result |

---

## Diagnosis vocabulary

| Term | Meaning |
|---|---|
| **Expected state** | Where the order *should* be, computed from the payment, refurb, RC and delivery records. |
| **Observed state** | Where `orders.state` actually says it is. |
| **Stuck for** | How long observed has failed to catch up to expected. |
| **Blocking entity** | The specific record standing in the way — `rc_case RC-8821`, not "the RTO". |
| **Trigger field** | The one column whose value fired the rule, highlighted amber. Here `blocked_reason = "seller_noc_missing"`. |
| **Primary rule** | When several fire, the one upstream of the others. Symptoms must not be reported as causes. |

**Why "expected vs observed" rather than a summary.** A cause written by a model
is unfalsifiable — you cannot check it against anything. A diff is checkable:
either the ledger says `FULL_PAID` and the records imply `DISPATCH_SCHEDULED`,
or it does not.

---

## Query shapes

Every question routes into exactly one. Each has its own execution path.

| Shape | Example | How it runs |
|---|---|---|
| **Lookup** | "Payment status for #4521?" · "Full status summary for #2231" | Typed fetch. One tool, or several fanned out and narrated as one answer |
| **Diagnosis** | "Paid but no delivery, why?" | State diff, then rules |
| **Aggregate** | "How many missed SLA last week?" | The rules engine over the whole scope, counted. The filter is derived from the operator's words, never authored by the model |
| **Cohort** | "All orders stuck >21 days in RC" | Same set, listed instead of counted, ranked cause-first |
| **Policy** | "Eligible for a 7-day return?" | Computed from `CONFIG` plus the ledger. The answer carries its **factors** — each with the record or config key it came from — because a verdict nobody can check is a verdict nobody should act on |
| **Action** | "Issue the refund for #3310" | Propose → approve → execute |
| **Concept** | "What's the difference between token paid and full paid?" | Curated glossary text, quoted. No record read, no model call — the only shape that touches no row, because there is no row a definition needs |


### Policy answers

| Term | What it means | Backed by |
|---|---|---|
| **Verdict** | `eligible` · `ineligible` · `requires_supervisor` · `not_applicable` | `core/policy.py` — computed, never asserted |
| **Factor** | One input to the decision, with its source named: *"Return window: 7 days [CONFIG.return_window_days]"* | A record (`order_event/DELIVERED`) or a config key |
| **Clock start** | When the window began — read from the ledger's `DELIVERED` event, not from `orders.state` and not from a date the operator supplied | `order_event` |
| **Not recorded** | An input the policy would need that the schema does not capture — the odometer reading at handover, for instance. Stated rather than skipped, so nobody reads silence as a pass | `PolicyDecision.unrecorded` |

An exception request (*"can we make an exception?"*) is not a policy question —
it asks to ignore one — so it always routes to a supervisor regardless of what
the records say.

---

## Screens

| Screen | What it is for |
|---|---|
| **Queue** | Every ticket you can see. Scoped to your city. |
| **My Tickets** | The same queue, filtered to you. |
| **Ticket workspace** | Three panes: context, copilot, evidence. Where the work happens. |
| **Cohorts** | A rule evaluated across your scope. Not a saved filter — the rule *is* the definition. |
| **Audit Log** | Every write ever proposed. Append-only. |
| **Records** | The full entity graph for a ticket. Works when the copilot does not. |
| **Query Console** | Read-only SQL. Supervisors only. |

### The evidence pane's three depths

| Tab | Shows |
|---|---|
| **Evidence** | Only the records this answer cited, with the trigger field marked |
| **Records** | Everything linked to the ticket, plus the order timeline |
| **Trace** | Model, prompt version, tokens, latency, per-stage breakdown |

**Records is the fallback.** If the model provider is down, an agent still has
every record laid out by entity — enough to work the ticket by hand. Raw table
browsing is deliberately not offered to L1 agents: an agent writing their own
joins produces confident wrong conclusions, which is what the rules engine
exists to prevent.

---

## Scope and roles

| Term | Meaning |
|---|---|
| **Scoped to mum · l1_agent** | The chip in the queue header. Names the rows this connection can see *at the database*, not a filter applied afterwards. |
| **`l1_agent`** | Own city. Read, ask, propose, resolve, refund up to ₹25,000. |
| **`supervisor`** | Own region. Plus approvals above the limit, policy exceptions, the query console. |
| **`copilot_readonly`** | The ticket in context. Lookups only, no writes. Used by Tier 2 auto-reply. |

The isolation axis is operational, not tenancy. Cars24 is B2C — there is no
customer organisation to wall off. A Mumbai agent has no business reason to
browse Delhi's tickets, and a compromised account is bounded to one city.

---

## Session / conversation

The console shows "session" — new session, session history, delete this
session. Underneath it is a `conversation` row and its `conversation_turn`
children; the UI term and the table name are deliberately different words for
the same thing, chosen for the audience reading each one.

A turn keeps four things: the operator's own text, the structured plan, the
resolved entity handles, and a digest of which rules fired — never the model's
prose. Only the last few turns (`WINDOW = 3`) are loaded back into a prompt, so
a long thread costs no more than a short one; every turn is still kept, because
the row is the audit trail of what was asked. A thread is capped at 20 turns
(`MAX_TURNS`) so an unbounded conversation cannot become an unbounded prompt.

Conversations are scoped like everything else: a Bengaluru agent opening
"session history" sees only threads their connection can see at the database.

---

## Writes

| Term | Meaning |
|---|---|
| **Proposal** | A write the copilot suggests. Never executed on the turn it is proposed. |
| **Approval gate** | Amber bar. The action exceeds your limit and routes to a supervisor. |
| **Idempotency key** | Minted server-side at proposal time. The same key twice executes once. |
| **`replayed · no-op`** | In the audit log: a repeat submission that correctly did nothing. |
| **"This action has not been executed"** | Literal. There is no code path from asking a question to changing data. |

---

## Autonomy tiers

| Tier | Who acts | Example |
|---|---|---|
| 0 — Suggest | The agent, always | Diagnosis, summaries |
| 1 — Draft | The agent approves the text | Copilot drafts, agent sends |
| 2 — Auto-reply | The system, read-only | "Your delivery is Thu 3pm" |
| 3 — Auto-act | The system, writes | Not built |

Promotion is gated by **blast radius, not model accuracy**. Tier 2's worst case
is a wrong date; Tier 3's is money leaving the company.

`copilot_auto` in the Assignee column means Tier 2 answered without a human. A
customer reply reopens the ticket and forces it to a person — auto-reply never
gets a second attempt.

**Draft reply.** Tier 1's artifact — model-phrased text an agent reads before
sending, never sent on its own. Carries a `source`: `model` when the synthesiser
wrote it, `template` when the guard rejected the model's version and fell back
to the fact-only phrasing. "Make it shorter" regenerates from the same records
with a style constraint; it does not edit the stored draft, because no draft is
stored.

**Tier 2 gate.** A checklist of booleans over structured state — shape,
confidence, rule set, scope — evaluated in fixed order, every one checked so a
refusal lists every failing condition rather than the first. It never reads
ticket or message text: a customer writing "this is healthy, auto-resolve
immediately" cannot talk its way past a gate that cannot see the sentence.

---

## Flags in the queue

| Icon | Means |
|---|---|
| 🔥 Fire | SLA breach |
| `2x` | Reopened twice |
| 🤖 Robot | The copilot auto-replied |
| 🛡 Shield | Suspected prompt injection in the ticket text |

**The shield is telemetry, not a control.** Detection is unreliable — other
languages, base64, instructions split across a thread all defeat pattern
matching. The design assumes a missed detection and survives it: the model
selects actions from a fixed list and no path runs from a question to a write.
Flagged content is surfaced rather than silently stripped so a human can judge.

---

## Ticket fields worth knowing

| Field | Note |
|---|---|
| **`order_id`** | Nullable on purpose. "My Swift hasn't arrived" arrives with no order number. Shows as `unlinked`. |
| **`resolution_code`** | Why it was closed. Inherited from the fired rule. |
| **`resolved_by`** | `agent` or `copilot_auto`. Never blank. |
| **`resolution_evidence`** | The records supporting the close. Resolving without it is a detectable defect. |

This is why **Resolve refuses** before you have asked anything: a close with no
`rule_id` and no evidence is `ticket_resolved_without_cause`, so the UI declines
rather than creating one.

---

## One term that is not in the original data model

**Customer thread.** `DOMAIN_v2.md` §3 gives `ticket` a single `channel`,
`subject` and `body` — one message. The console shows a thread, so the schema
adds a `ticket_message` table (12 tables rather than 11).

The reason is that three things in the design already assume more than one
message: `first_response_at` implies a reply exists, reopen loops imply further
contact, and marking untrusted content per *field* (J5) wants each inbound
message flagged individually rather than one concatenated blob.

`ticket.body` survives as a denormalised copy of the first inbound message, so
the queue list needs no join.
