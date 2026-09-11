---
name: Precision Operations Console
colors:
  surface: '#faf8ff'
  surface-dim: '#d2d9f4'
  surface-bright: '#faf8ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f2f3ff'
  surface-container: '#eaedff'
  surface-container-high: '#e2e7ff'
  surface-container-highest: '#dae2fd'
  on-surface: '#131b2e'
  on-surface-variant: '#464555'
  inverse-surface: '#283044'
  inverse-on-surface: '#eef0ff'
  outline: '#777587'
  outline-variant: '#c7c4d8'
  surface-tint: '#4d44e3'
  primary: '#3525cd'
  on-primary: '#ffffff'
  primary-container: '#4f46e5'
  on-primary-container: '#dad7ff'
  inverse-primary: '#c3c0ff'
  secondary: '#4e45d5'
  on-secondary: '#ffffff'
  secondary-container: '#6860ef'
  on-secondary-container: '#fffbff'
  tertiary: '#7e3000'
  on-tertiary: '#ffffff'
  tertiary-container: '#a44100'
  on-tertiary-container: '#ffd2be'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#e2dfff'
  primary-fixed-dim: '#c3c0ff'
  on-primary-fixed: '#0f0069'
  on-primary-fixed-variant: '#3323cc'
  secondary-fixed: '#e3dfff'
  secondary-fixed-dim: '#c3c0ff'
  on-secondary-fixed: '#100069'
  on-secondary-fixed-variant: '#372abf'
  tertiary-fixed: '#ffdbcc'
  tertiary-fixed-dim: '#ffb695'
  on-tertiary-fixed: '#351000'
  on-tertiary-fixed-variant: '#7b2f00'
  background: '#faf8ff'
  on-background: '#131b2e'
  surface-variant: '#dae2fd'
typography:
  display-sm:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Inter
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
    letterSpacing: -0.015em
  headline-md:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '600'
    lineHeight: 24px
    letterSpacing: -0.01em
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
    letterSpacing: 0em
  body-sm:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 18px
    letterSpacing: 0em
  label-md:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.01em
  label-sm:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: '600'
    lineHeight: 14px
    letterSpacing: 0.03em
  mono-data:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: -0.01em
  mono-metric:
    fontFamily: JetBrains Mono
    fontSize: 14px
    fontWeight: '600'
    lineHeight: 20px
    letterSpacing: -0.02em
  display-sm-mobile:
    fontFamily: Inter
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
    letterSpacing: -0.01em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  space-2xs: 0.125rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 0.75rem
  space-lg: 1rem
  space-xl: 1.25rem
  space-2xl: 1.5rem
  space-3xl: 2rem
  table-row-h-dense: 2rem
  table-row-h-default: 2.5rem
  sidebar-width: 16rem
  copilot-dock-width: 24rem
---

## Brand & Style

This design system is engineered for mission-critical enterprise workflows, operations visibility, and intelligent agent monitoring. Its audience comprises operations directors, platform reliability engineers, and technical analysts who demand instantaneous comprehension, high situational awareness, and zero ambiguity under pressure.

The aesthetic balance merges high-performance technical precision with the refined ergonomics of state-of-the-art AI copilot environments:
- **Design Archetype:** Precision Minimalist SaaS with high-density data architecture.
- **Visual Stance:** Calm, authoritative, and frictionless. Utilitarian structures are softened by micro-refinements, precise optical borders, and intentional tonal contrast.
- **Feedback & Dynamics:** Real-time state shifts are clear and discrete. Information density takes precedence over decorative negative space, ensuring high screen real estate utility without visual fatigue.

## Colors

The palette establishes an unambiguous hierarchy between primary application navigation, critical operational telemetry, and surrounding structural frame surfaces:

- **Primary (`#4f46e5`, `#4338ca`):** Anchors main actions, selected row states, focus halos, and active AI copilot threads.
- **Slate Neutrals:** Form a crisp background matrix. Ground level (`#f8fafc`) sets the canvas; secondary structural cards and sidebars use pure white (`#ffffff`) with hair-thin borders (`#e2e8f0`). Secondary hover layers deploy `#f1f5f9`.
- **Operational Semantic Palette:**
  - **Emerald (`#10b981`):** Indicates verified system states, complete reconciliations, and healthy telemetry.
  - **Amber (`#f59e0b`):** Dictates degraded performance, queued ingestion batches, and required intervention.
  - **Rose (`#f43f5e`):** Signals SLA breaches, execution failures, pipeline stalls, and hard limits.
  - **Indigo (`#4f46e5`):** Denotes active operations, synthesis jobs in flight, and active agent threads.
- **Accessibility:** All operational status text must exceed 4.5:1 contrast against ambient container backgrounds. Indicators pair chromatic signals with explicit text or icon glyphs for clear data comprehension.

## Typography

Typography governs readability across massive datasets without inducing visual strain:

- **Inter (Sans-Serif):** Employs standard tracking and tabular numbers (`tnum`) across tables and UI surfaces. Headlines remain low-profile and compact, maximizing viewport utility for core operational metrics.
- **JetBrains Mono (Monospace):** Dedicated strictly to telemetry strings, run IDs, payload schemas, hash digests, latency figures, and code executions. Monospace units keep character widths visually aligned across consecutive table rows.
- **Vertical Rhythm:** Line heights match standard 4px baseline alignments, ensuring inline badges, status dots, and text strings remain aligned.

## Layout & Spacing

This layout system operates on an internal base-4 grid (`0.25rem` / `4px`), prioritizing functional space allocation and high viewport utilization:

- **Structural Layout:** A 3-zone architecture consisting of a collapsible operational navigation rail (256px), a flexible telemetry work-surface (`minmax(0, 1fr)`), and an integrated AI copilot dock (384px) that docks on the right or collapses into an overlay.
- **Density Modes:**
  - **High-Density (Default Data Mode):** Table rows sit at `32px` (`2rem`), cell padding at `8px` horizontal (`space-sm`), compact action bars, and inline micro-badges.
  - **Standard Mode (Overview/Dashboard):** Table rows expand to `40px` (`2.5rem`), card margins increase to `16px` (`space-lg`).
- **Responsive Adaptations:**
  - **Desktop (>= 1280px):** Full simultaneous 3-zone display. 
  - **Tablet (768px - 1279px):** Copilot collapses into a slide-over panel; navigation rails convert to compact icon bars (56px).
  - **Mobile (< 768px):** Single-column layout. High-density grids convert into stacked summary cards with key metrics pinned to the right edge.

## Elevation & Depth

Visual hierarchy is built using tonal layering and low-contrast borders rather than pronounced drop shadows:

- **Surface Levels:**
  - **Canvas (Level 0):** `#f8fafc` — Base environment.
  - **Surface (Level 1):** `#ffffff` with a crisp `1px` outline of `#e2e8f0`. Used for data tables, metrics panels, and analytical cards.
  - **Surface Raised (Level 2):** `#ffffff` with a `1px` outline of `#cbd5e1` and an ambient shadow: `0 1px 3px 0 rgba(15, 23, 42, 0.04), 0 1px 2px -1px rgba(15, 23, 42, 0.03)`. Used for dropdowns, popovers, and sticky control headers.
  - **Surface Overlay (Level 3):** `#ffffff` with a `1px` border of `#cbd5e1` and shadow: `0 10px 15px -3px rgba(15, 23, 42, 0.08), 0 4px 6px -4px rgba(15, 23, 42, 0.04)`. Reserved for slide-over inspector sheets, filter builders, and modals.
- **Dividers & Focus Outlines:** Subtle `1px` `#f1f5f9` or `#e2e8f0` dividers maintain row separation. Dynamic focus states produce a crisp `2px` offset ring using `indigo-600` at 100% opacity without soft shadow bleeding.

## Shapes

The design system implements a soft, calibrated corner radius scale:

- **Base Radius (`0.25rem` / `4px`):** Applied to form controls, compact data cells, dropdown triggers, status indicators, and inner table widgets.
- **Container Radius (`0.5rem` / `8px`):** Applied to core metrics cards, panels, copilot interaction bubbles, and data grid enclosures.
- **Overlay Radius (`0.75rem` / `12px`):** Applied exclusively to floating command palettes (`Cmd+K`) and root modal dialogues.
- **Geometry Stance:** Rounded pills and circular shapes are avoided except for status indicator dots (6px) and user avatars. Tight radii keep visual weight low and retain strict table and column alignment.

## Components

### Buttons & Action Triggers
- **Primary:** Background `indigo-600` (`#4f46e5`), text `#ffffff`, hover `indigo-700` (`#4338ca`), active `indigo-900`. Compact `32px` height, `12px` horizontal padding, `4px` radius. Font: Inter, 13px, weight 500.
- **Secondary / Outline:** Background `#ffffff`, border `1px` `#e2e8f0`, text `slate-800` (`#0f172a`), hover background `#f1f5f9`, hover border `#cbd5e1`.
- **Ghost / Table Action:** Borderless, text `slate-600`, hover background `#f1f5f9`, padding `4px 8px`. Used for inline row menus and utility actions.

### High-Density Data Tables
- **Header:** Height `32px`, background `#f8fafc`, text uppercase `slate-500` (`11px`, weight 600, letter-spacing `0.03em`), bottom border `1px` `#e2e8f0`. Sticky positioning.
- **Rows:** Alternating rows inactive by default; pure white background with `1px` border-bottom `#f1f5f9`. Row hover applies `#f8fafc`. Selected state applies `#eef2ff` with a `2px` inset primary indicator on the leftmost edge.
- **Cells:** Padding `6px 12px`. Aligned text defaults to left; numbers and timestamps use `font-mono` (`JetBrains Mono`, `12px`) and align to the right.

### Status Indicators & Badges
- **Pill Badge:** Height `20px`, padding `0 6px`, radius `4px`. Composed of a solid `6px` status dot, followed by `11px` weight 600 text.
  - *Resolved/Verified:* Background `#ecfdf5`, border `#a7f3d0`, dot `#10b981`, text `#047857`.
  - *Warning/Pending:* Background `#fffbeb`, border `#fde68a`, dot `#f59e0b`, text `#b45309`.
  - *Breach/Stall:* Background `#fff1f2`, border `#fecdd3`, dot `#f43f5e`, text `#be123c`.
  - *In-Progress/Active:* Background `#eef2ff`, border `#c7d2fe`, dot `#4f46e5`, text `#4338ca`.

### Form Controls & Filters
- **Inputs:** Height `32px`, border `1px` `#cbd5e1`, background `#ffffff`, text `13px` `#0f172a`, placeholder `#94a3b8`. Focus state uses outline `2px` solid `#4f46e5` with `0px` outline offset.
- **Checkboxes & Radios:** `14px × 14px`, border `1px` `#cbd5e1`, radius `3px` for checkboxes, circular for radios. Checked state background `#4f46e5` with white check glyph.

### Cards & Metrics Panels
- **Structure:** Solid `#ffffff` background with `1px` `#e2e8f0` border, `8px` corner radius. 
- **Content Flow:** Upper row displays metric title (`12px` `slate-500`) and optional badge; middle row features large numerical readout (`20px` `JetBrains Mono` bold); footer provides contextual micro-trend indicators (`11px` monospace with up/down arrows).

### AI Copilot Interaction Module
- **Docked Container:** Fixed `384px` wide panel, left border `1px` `#e2e8f0`, background `#ffffff`.
- **Response Cards:** Message bubbles use `#f8fafc` with `1px` `#e2e8f0` border, `6px` radius. Monospaced inline citations reference live dataset indices (`[Row 1428]`), hovering over which highlights the corresponding table row on the main canvas.