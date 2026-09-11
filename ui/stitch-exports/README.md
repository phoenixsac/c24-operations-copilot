# Stitch exports — raw, do not edit

Drop the untouched **Code** export from Stitch here, one file per screen:

```
screen-2-workspace.html     ← generate + export first (palette anchor)
screen-1-queue.html
screen-3-records.html
screen-4-approval.html
```

These are the source of truth for what Stitch produced. Never hand-edit them —
if a screen is wrong, re-prompt in Stitch and re-export over the top. Hand-edits
here get silently lost on the next export and the diff becomes unreadable.

## What the export actually contains

- One flat HTML file, no components
- Tailwind v3 via CDN `<script src="https://cdn.tailwindcss.com">`
- Google Material Symbols via a `<link>` font, icons as `<span class="material-symbols-outlined">`
- Hardcoded placeholder copy, sometimes not the copy from the prompt
- Placeholder image URLs pointing at Google-hosted assets

None of that survives into `src/`. The conversion (see `../STITCH_INTEGRATION.md`)
strips the CDN, replaces icons, and swaps placeholder copy for props fed by
`src/api`.

## Viewing one without the build

```bash
open ui/stitch-exports/screen-2-workspace.html
```

It renders standalone because of the CDN. That is the only thing the CDN is for.
