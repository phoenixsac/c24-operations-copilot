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
| **Confidence** | A number, `0.91`. Thresholded, not decorative — the Tier 2 gate consumes it. | Emitted with every answer. |
| **Cited evidence** | Chips naming the exact records the answer rests on: `payment #P-9912`. | Only records actually retrieved. No claim appears without one. |
| **Propose action** | A button. Names an action from a fixed list. | The rules engine produced the list. The model selects; it cannot author one. |

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
| **Aggregate** | "How many missed SLA last week?" | SQL |
| **Cohort** | "All orders stuck >21 days in RC" | SQL, then rules per row |
| **Policy** | "Eligible for a 7-day return?" | Policy evaluated as data |
| **Action** | "Issue the refund for #3310" | Propose → approve → execute |

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
