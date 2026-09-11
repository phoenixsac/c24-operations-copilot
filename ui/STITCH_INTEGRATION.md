# Stitch export → working UI

How a raw Stitch HTML export becomes a wired React screen. Same six steps every
screen; screen 2 is the only one that takes real thought.

## 0. Export from Stitch

In the Stitch project, open the screen, then **Code → copy/download the HTML**.
(The other option, *Copy to Figma*, gives you a design file, not markup — useful
for handing to a designer, useless here.)

Save it **untouched** as `stitch-exports/screen-N-<name>.html`. See that
directory's README for why it stays untouched.

## 1. Strip the standalone scaffolding

The export is built to open on its own, so it carries things the Vite app already
provides. Delete:

| In the export | Why it goes |
|---|---|
| `<script src="https://cdn.tailwindcss.com">` | Tailwind is compiled by PostCSS here |
| Any inline `tailwind.config = {...}` | Tokens live in `tailwind.config.js` |
| `<html>`, `<head>`, `<body>` wrappers | You only want the body's inner markup |
| Google Fonts / Material Symbols `<link>` | See step 3 |
| Placeholder image URLs | Replace with a local asset or a coloured `div` |

What survives is one big tree of `<div class="...">`.

## 2. Convert HTML to JSX

Mechanical. `class` → `className`, `for` → `htmlFor`, self-close `<img>`/`<br>`,
`style="a: b"` → `style={{ a: 'b' }}`, and comments become `{/* */}`.

Then reconcile the palette. Stitch hardcodes hex values that the design system
already names — swap them for the tokens so the screens stay consistent:

| Stitch emits | Use instead |
|---|---|
| `bg-[#F7F8FA]` | `bg-canvas` |
| `border-[#E4E7EC]` | `border-hairline` |
| `text-[#4F46E5]` / `bg-[#4F46E5]` | `text-accent` / `bg-accent` |
| `text-[#059669]` | `text-healthy` |
| `text-[#D97706]` | `text-atrisk` |
| `text-[#DC2626]` | `text-breached` |
| `text-[#6B7280]` | `text-muted` |
| `text-[13px]` / `text-[12px]` / `text-[15px]` | `text-body` / `text-meta` / `text-head` |

Anything numeric — IDs, amounts, timestamps — also gets `tnum`.

## 3. Icons

Material Symbols arrive as `<span class="material-symbols-outlined">rule</span>`.
Either add the font `<link>` to `index.html` and keep them, or replace each with
an inline SVG. Keeping the font is faster and fine for a demo; note it as a
dependency if the console is meant to work offline.

## 4. Split into components

Cut along the panes, not along arbitrary div boundaries. For screen 2:

```
src/screens/TicketWorkspace.tsx      three-pane shell + top bar
src/components/TicketContextPane.tsx left  — customer, order, messages
src/components/CopilotThread.tsx     centre — transcript + composer
src/components/AnswerCard.tsx        centre — ONE copilot answer
src/components/EvidencePane.tsx      right — segmented Evidence/Records/Trace
```

**`AnswerCard` is the one to get right.** It is the product thesis rendered:
verdict line → diagnosis strip → rule chips → explanation → evidence chips →
action footer. If Stitch returned it as a plain chat bubble, re-prompt that
section alone rather than fixing it by hand — the doc's own note says so.

It has four states, all already present in the fixtures:

| State | Fixture | Looks like |
|---|---|---|
| Diagnosis | `ANSWER_DIAGNOSIS` | Full card, red rule chip, propose-action button |
| Refusal | `ANSWER_REFUSAL` | Grey card, italic, evidence pointers, "Insufficient data" pill |
| Proposal | `ANSWER_PROPOSAL` | Amber approval gate, idempotency key, "not executed" |
| Degraded | `ANSWER_DEGRADED` | Names the unavailable source, no invented rules |

Build all four. A card that only renders the happy path hides exactly the
properties the design is arguing for.

## 5. Replace placeholder copy with props

Stitch hardcodes strings. Every one of them becomes a prop fed from `src/api`.
The types in `src/types/api.ts` tell you what is actually available — if the
markup wants a field that isn't in the type, that is a design/backend mismatch
to resolve **now**, not a reason to widen the type.

```tsx
// before (Stitch)
<p className="font-medium">Payment is fine. Delivery is blocked on RC transfer.</p>

// after
<p className="font-medium">{answer.verdict}</p>
```

Two rules while doing this:

- **Never render `ticket.body` or any customer text as HTML.** JSX escapes by
  default; do not reach for `dangerouslySetInnerHTML`. That is invariant J12,
  and the console is an injection sink for the browser if you break it.
- **Identity fields come from the API, not from model output.** Name and phone
  are rehydrated from the database keyed by id (H3). The answer payload has no
  name field, on purpose.

## 6. Verify

```bash
npm run dev        # http://localhost:5173
npm run typecheck
```

Screen is done when all four `AnswerCard` states render from fixtures with no
hardcoded strings left in the component.

---

## Screen order

`2 → 1 → 3 → 4`. Screen 5 (query console) is on the skip list in
`docs/SCOPE.md` §3 — the Records view is the real fallback. Generate it only
with spare Stitch credits.

Two corrections to make **before** pasting a prompt:

- Screen 5's banner reads `tenant_id = 'mum-01'`. Wrong. The scoping key is
  `city_code` / `region`; this is B2C and there is no tenant. Use
  `-- city_code = 'mum' is applied automatically to all queries`.
- Screen 1's stat card "Auto-resolved today 5" only makes sense if Tier 2 ships.
  It is the first thing cut per `docs/SCOPE.md` §4 — keep the card, but drive it
  from real data rather than leaving it hardcoded at 5.
