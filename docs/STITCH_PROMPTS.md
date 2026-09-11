# Google Stitch Prompts — Ops Copilot UI

Five screens. Paste the design system block at the top of **every** prompt, then the screen prompt below it. Generate one screen per session; Stitch degrades when asked for multiple layouts at once.

---

## Design system preamble (paste before each screen prompt)

```
Design system for all screens:

Product: an internal operations console for a used-car marketplace. Users are
support agents working a queue of customer tickets. This is a dense professional
tool, not a consumer app. Prioritise information density over whitespace.

Style: clean enterprise SaaS, similar to Linear or Height. Light theme.
Neutral grey background (#F7F8FA), white cards, 1px subtle borders (#E4E7EC),
6px corner radius, minimal shadows.

Type: Inter. 13px body, 12px labels and metadata, 15px headings. Tabular
numerals for IDs, amounts and timestamps.

Accent: deep indigo (#4F46E5) for primary actions and links.
Status colours: green (#059669) healthy/resolved, amber (#D97706) at-risk/waiting,
red (#DC2626) breached/blocked, grey (#6B7280) closed/neutral.

Every status is a small pill with a coloured dot, never colour alone.
Money shown in Indian format with ₹ and lakh notation where large.
Timestamps relative ("62h ago") with absolute on hover.
```

---

## Screen 1 — Ticket Queue

```
Design a ticket queue screen for the operations console.

Left sidebar, 220px, collapsible: product name "Copilot" at top, then nav items
with icons — Queue (active), My Tickets, Cohorts, Audit Log, Query Console
(this one shows a small "Supervisor" badge). At the bottom, a user chip showing
avatar, name "Priya Nair", and role "L1 Agent".

Main area: header row with the title "Ticket Queue", a live count "34 open",
and on the right a search input and a "Filters" button.

Below the header, a horizontal row of four small stat cards: "Unassigned 12",
"SLA breach 3" (red), "Awaiting customer 8" (amber), "Auto-resolved today 5"
(with a small robot icon).

Then a dense data table, one row per ticket, with these columns:
- Priority (small coloured bar)
- Ticket ID (mono, e.g. TKT-4821)
- Subject (truncated, e.g. "Paid but no delivery date")
- Customer name and city, stacked in two lines
- Linked order (e.g. #1289, or a grey "unlinked" pill when absent)
- State pill (Open / Assigned / In Progress / Awaiting Customer / Resolved)
- Flags column: small icons for SLA breach, reopened count, and a robot icon
  where the copilot auto-replied
- Age ("62h")
- Assignee avatar, or "Assign" button when unassigned

Rows are ~44px tall, alternating subtle background. Three rows should show a red
left border for SLA breach. One row should show a small orange shield icon with
tooltip text "flagged content" to represent a ticket containing a suspicious
instruction.

Hovering a row reveals a right-aligned "Open" button.
```

---

## Screen 2 — Ticket Workspace (the main screen)

```
Design the main ticket workspace: a three-pane layout, no page scroll, each pane
scrolls independently.

Top bar spanning full width: back arrow, ticket ID "TKT-4821", subject
"Paid but no delivery date", a state pill "In Progress", an SLA chip
"First response 2h left" in amber, assignee avatar, and on the right two buttons:
"Resolve" (primary indigo) and a "..." overflow menu.

LEFT PANE (300px) — Ticket context:
- Customer card: name, phone, city, "3 previous tickets" link
- Linked order card: order ID #1289, vehicle "2019 Maruti Swift VXI",
  reg no "MH12AB1234", amount "₹6.2L", current state pill "FULL_PAID"
- A vertical timeline of the customer's messages in the thread, each with
  channel icon (WhatsApp / email), timestamp, and body text. Messages sit in
  light grey bubbles with a small label "Customer message — read only" above
  the first one.
- At the bottom, a collapsed section header "Order state timeline (9 events)"

CENTRE PANE (flexible, widest) — Copilot conversation:
- Header "Copilot" with a small model chip "sonnet" and a latency chip "1.2s"
- Chat transcript. The agent's messages are right-aligned plain text. The
  copilot's answers are left-aligned structured cards, not plain bubbles.
- Show one copilot answer card containing, in order:
    1. A one-line verdict in medium weight: "Payment is fine. Delivery is
       blocked on RC transfer."
    2. A diagnosis strip: three small boxes side by side reading
       "Expected: DISPATCH_SCHEDULED", "Observed: FULL_PAID", "Stuck: 62h"
    3. A rule chip row: a red pill "rc_transfer_stall v2" and a grey pill
       "confidence 0.91"
    4. Two or three sentences of explanation
    5. An evidence row: three small chips "payment #P-9912", "rc_case RC-8821",
       "order_event #7" — each chip has a link icon
    6. A footer row of buttons: "Show trace", "Draft reply", and a primary
       button "Propose action: Escalate to RTO"
- Below that, a second shorter copilot message showing a refusal state: grey
  card, italic text "No data supports this — the order has no warranty SKU",
  with two evidence chips and a muted "Insufficient data" pill.
- At the bottom, a message composer with placeholder "Ask about this ticket…",
  a send button, and three suggestion chips: "Full status summary",
  "Why is this stuck?", "Draft customer reply".

RIGHT PANE (340px) — Evidence:
- Segmented control at top with three options: "Evidence" (active), "Records",
  "Trace"
- Under Evidence: a list of the exact records the copilot cited. Each is a
  compact card showing table name in mono, record ID, and 3 or 4 key fields as
  label/value pairs. Highlight in amber the specific field that triggered the
  rule — here rc_case.blocked_reason = "seller_noc_missing".
- A footnote at the bottom in small grey text: "Showing 3 cited records.
  Switch to Records for all data linked to this ticket."
```

---

## Screen 3 — Records Explorer (fallback view)

```
Design the "Records" tab of the right-hand evidence pane, shown expanded to full
width as a modal overlay, 900px wide, over a dimmed background.

Header: "All records for TKT-4821" with a close X, and a note in small grey text
"Read only. This view works when the copilot is unavailable."

Left rail inside the modal, 180px: a tree of linked entities with record counts —
  Ticket (1)
  └ Order #1289 (1)
     ├ Payments (2)
     ├ Refunds (0)
     ├ RC Case (1)
     ├ Refurb Job (1)
     ├ Delivery (0)
     ├ Vehicle (1)
     └ Order Events (9)
Entities with zero records are greyed. "RC Case" is selected and shows a small
red dot indicating a rule fired on it.

Main area: the selected entity rendered as a vertical key/value table, field name
in grey on the left, value in mono on the right, ~28px rows. The field
"blocked_reason" is highlighted amber with a small rule chip beside it reading
"rc_transfer_stall".

Below the key/value table, a section titled "Order state timeline" showing a
horizontal stepper: CREATED → TOKEN_PAID → FULL_PAID → REFURB_DONE → RC_DONE →
DISPATCH_SCHEDULED → DELIVERED. Completed steps are green with check icons,
the current step FULL_PAID is a solid indigo dot, RC_DONE is red with a warning
icon, and everything after it is greyed out. Under the stepper, a caption
"Expected to be at DISPATCH_SCHEDULED. Stuck 62h at FULL_PAID."
```

---

## Screen 4 — Action Approval

```
Design an action approval modal, 560px wide, centred over a dimmed background.

Header: "Approve action" with a shield icon.

Body:
- A summary block: action name "Issue refund" in medium weight, then a
  key/value list — Order #3310, Customer "Rahul Menon", Amount "₹6,20,000",
  Reason "duplicate charge detected".
- A "Why this was proposed" section: a red rule chip "refund_duplication v1"
  and two evidence chips "payment #P-8801", "refund #R-2210".
- An amber warning bar with a lock icon reading: "Above your approval limit of
  ₹25,000. Supervisor approval required." Below it a small row showing
  "Routing to: Anil Kumar (Supervisor)".
- A collapsed grey row in mono showing "idempotency key: a3f9c2…" with a small
  info icon.

Footer: a "Cancel" ghost button on the left and, on the right, a primary button
that is DISABLED and reads "Request supervisor approval". Underneath in small
grey text: "This action has not been executed."

Also generate a second variant of the same modal where the user IS a supervisor:
no amber warning bar, and the primary button is enabled and reads "Approve and
execute".
```

---

## Screen 5 — Query Console (supervisor only)

```
Design a read-only SQL query console screen for supervisors.

Header: "Query Console" with a "Supervisor" badge, and on the right a small
amber chip reading "Read only · 500 row limit · 5s timeout".

Left sidebar, 200px: a schema browser listing tables — customers, vehicles,
orders, order_events, payments, refunds, rc_cases, refurb_jobs, deliveries,
tickets. Each expands to show column names in mono with type labels in grey.

Main area, split horizontally:
- TOP: a code editor with SQL syntax highlighting, showing a query like
  "SELECT o.id, o.state, r.blocked_reason FROM orders o JOIN rc_cases r ON …"
  Above the editor, a grey banner in mono reading:
  "-- city_code / region scoping is applied by the database to every query"
  (There is no tenant. This is B2C; the scoping keys are city_code and region.)
  Below the editor, a "Run" button and a saved-queries dropdown containing
  entries like "Stuck in RC > 21d" and "Refund duplicates".
- BOTTOM: a results grid, dense, with mono values, showing about 8 rows and a
  footer reading "8 rows · 412ms". Each row has a small "Open ticket" link in
  the last column.

At the very bottom of the screen, a thin grey bar with an info icon:
"All queries are logged to the audit trail."
```

---

## Notes for iterating in Stitch

- Generate Screen 2 first. It's the one that carries the whole concept; the others should be adjusted to match whatever palette and density Stitch settles on there.
- If a pane comes back too airy, re-prompt with "reduce vertical padding by half, this is a dense operations tool."
- The structured answer card in Screen 2 is the thing to protect. If Stitch renders it as a plain chat bubble, re-prompt that section alone: "the assistant response is a structured card with a verdict line, a three-box diagnosis strip, rule chips, and an evidence chip row — not a text bubble."
- Ask for a mobile variant only after desktop is settled. Realistically ops agents work on desktop, and saying so in DESIGN.md is a legitimate scope decision.
