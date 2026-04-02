# EDQ Design System — Tokens

This file is a design reference for visual tokens and styling intent. It is not
the current operational guide for setup, deployment, or backend behavior.

## Philosophy
Apple-style minimal. Clean solid dark surfaces. No noise, no clutter, no gradients on backgrounds.
Gradients reserved ONLY for accent elements (primary buttons, active indicators, key badges).
Every element earns its place through function, not decoration.
Premium feel comes from typography, spacing, and restraint — not effects.

---

## Colours

### Surfaces — Dark Mode (solid, never gradient)
- Background: #0b1120 (dark-bg — deep navy)
- Surface raised: #111827 (dark-surface — cards, panels)
- Card: #1e293b (dark-card — elevated cards)
- Sidebar: #0f172a (surface-sidebar — darker navy)
- Hover: #1e293b (dark-hover — same as card)

### Surfaces — Light Mode
- Background: #fafafa (surface — near white)
- Card: #ffffff (surface-card)
- Hover: #f4f4f5 (surface-hover)

### Borders
- Dark mode: #1e3a5f (dark-border — subtle navy)
- Light mode: #e4e4e7 (surface-border)

### Text
- Muted: #71717a (surface-muted — timestamps, hints)

### Text
- Primary: #fafafa (zinc-50 — almost white, not pure white)
- Secondary: #a1a1aa (zinc-400 — descriptions, labels)
- Muted: #71717a (zinc-500 — timestamps, hints)
- Disabled: #52525b (zinc-600)

### Accent Gradients (ONLY for primary buttons, active nav, key highlights)
- Gradient A (blue-to-purple): linear-gradient(135deg, #6366f1, #8b5cf6, #a855f7)
  CSS: bg-gradient-to-br from-indigo-500 via-violet-500 to-purple-500
- Gradient B (amber-to-pink): linear-gradient(135deg, #f59e0b, #ec4899)
  CSS: bg-gradient-to-br from-amber-500 to-pink-500

Use Gradient A as the default primary accent.
Use Gradient B sparingly for secondary highlights or to distinguish elements.

### Accent Solids (for text, icons, small indicators where gradient is too heavy)
- Accent text: #818cf8 (indigo-400)
- Accent icon: #a78bfa (violet-400)

### Verdict / Status Colours (from tailwind config)
- Pass: #16a34a (green-600)
- Fail: #dc2626 (red-600)
- Advisory: #d97706 (amber-600)
- Qualified: #ca8a04 (yellow-600)
- N/A: #71717a (zinc-500)
- Pending: #2563eb (blue-600)
- Info: #0891b2 (cyan-600)

### Status Badges
- Pass: Success text on Success background, 9999px radius (pill)
- Fail: Danger text on Danger background, pill
- Warning: Warning text on Warning background, pill
- N/A: Muted text on zinc-800, pill
- Running: Accent text on indigo-500/10 background, pill
- Pending: Disabled text on zinc-800, pill

---

## Typography

### Font Stack (from tailwind config)
- Primary: "Inter", system-ui, -apple-system, sans-serif
- Monospace: "JetBrains Mono", "Fira Code", monospace
- Load Inter from Google Fonts (weights: 400, 500, 600, 700)
- Load JetBrains Mono (weight: 400, 500)

### Scale
- Display: 36px / 2.25rem, weight 700, letter-spacing -0.025em, line-height 1.1
- H1: 30px / 1.875rem, weight 700, letter-spacing -0.025em, line-height 1.2
- H2: 24px / 1.5rem, weight 600, letter-spacing -0.02em, line-height 1.3
- H3: 20px / 1.25rem, weight 600, letter-spacing -0.01em, line-height 1.4
- Body: 14px / 0.875rem, weight 400, line-height 1.5
- Body small: 13px / 0.8125rem, weight 400, line-height 1.5
- Caption: 12px / 0.75rem, weight 500, uppercase, letter-spacing 0.05em
- Monospace body: 13px / 0.8125rem, weight 400

### Key Rules
- Negative letter-spacing on ALL headings (this creates the Apple feel)
- Never use font-weight below 400 or above 700
- Body text always 14px — never 16px (tighter, more professional)
- Use weight 500 (medium) for labels and nav items — not bold, not regular
- Uppercase + letter-spacing ONLY for category headers and small labels

---

## Spacing

### Base Unit: 4px
- 1: 4px (0.25rem)    — tight inner padding
- 2: 8px (0.5rem)     — between related items
- 3: 12px (0.75rem)   — input padding, small card padding
- 4: 16px (1rem)      — standard card padding, gaps
- 5: 20px (1.25rem)   — section padding
- 6: 24px (1.5rem)    — between card groups
- 8: 32px (2rem)      — between major sections
- 10: 40px (2.5rem)   — page-level padding
- 12: 48px (3rem)     — hero spacing

### Layout
- Sidebar width: 240px
- Top bar height: 56px
- Card padding: 16px (small cards), 20px (medium), 24px (large)
- Page content max-width: 1200px
- Page horizontal padding: 32px

---

## Borders & Radius

### Border Radius
- none: 0px (tables, terminal output)
- sm: 6px (inputs, small elements)
- md: 8px (cards, buttons)
- lg: 12px (modals, large cards)
- xl: 16px (hero cards, page panels)
- full: 9999px (pills, badges, avatars)

### Border Width
- Default: 1px
- Active/focus: 1px (change colour, not width — Apple style)
- Never use 2px borders — too heavy

---

## Shadows (minimal — Apple uses shadows sparingly on dark themes)
- None: most elements have no shadow on dark backgrounds
- Subtle: 0 1px 2px rgba(0,0,0,0.3) — only for floating elements (dropdowns, modals)
- Medium: 0 4px 12px rgba(0,0,0,0.4) — modals only
- Never use coloured shadows or glow effects

---

## Buttons

### Primary (gradient accent — the ONLY place gradients appear on interactive elements)
- Background: Gradient A (blue-to-purple)
- Text: white, weight 500
- Radius: 8px
- Padding: 10px 20px
- Hover: slightly brighter (opacity or lighter gradient stop)
- No border, no shadow

### Secondary (subtle, outlined)
- Background: transparent
- Border: 1px solid zinc-700 (#3f3f46)
- Text: zinc-200 (#e4e4e7), weight 500
- Hover: background zinc-800 (#27272a)

### Ghost (text only)
- Background: transparent
- No border
- Text: zinc-400 (#a1a1aa), weight 500
- Hover: text zinc-200

### Danger
- Background: rgba(248, 113, 113, 0.15)
- Text: red-400 (#f87171)
- Border: 1px solid rgba(248, 113, 113, 0.2)

---

## Inputs
- Background: #18181b (zinc-900)
- Border: 1px solid #27272a (zinc-800)
- Text: #fafafa
- Placeholder: #71717a (zinc-500)
- Focus border: #3f3f46 (zinc-700) — subtle brightening, not a glow
- Focus ring: none (Apple doesn't use focus rings on dark themes, uses border change)
- Radius: 6px
- Padding: 10px 12px
- Font: 14px Inter

---

## Cards
- Background: #18181b (zinc-900, raised surface)
- Border: 1px solid #27272a (zinc-800)
- Radius: 12px
- Padding: 20px
- No shadow
- Hover (if interactive): border brightens to zinc-700

---

## Tables
- Header: Caption style (12px, uppercase, letter-spacing, zinc-500 text)
- Header background: transparent (no fill — Apple style)
- Row divider: 1px solid #1c1c1f (almost invisible)
- Row hover: zinc-900/50 (very subtle)
- Cell padding: 12px 16px

---

## Terminal / Code Output
- Background: #0c0c0e (darker than page background)
- Border: 1px solid #1c1c1f
- Radius: 8px
- Font: JetBrains Mono 13px
- Text colour: #d4d4d8 (zinc-300)
- Padding: 16px
- Line numbers: zinc-600

---

## Navigation (Sidebar)
- Item text: zinc-400, weight 500, 14px
- Item hover: zinc-200 text, zinc-800/50 background
- Item active: zinc-50 text, small Gradient A left border (3px), zinc-800/30 background
- Item padding: 8px 16px
- Item radius: 6px
- Section headers: Caption style (12px uppercase, zinc-600)
- Icon size: 18px, zinc-500 (active: zinc-200)

---

## Animation (minimal)
- Transitions: 150ms ease (Apple standard)
- Hover transitions: background-color, border-color, color only
- No bounce, no elastic, no spring physics
- Loading spinner: simple rotation, accent colour, 1.5px stroke
- Progress bar: smooth width transition 300ms
- Page transitions: none (instant — Apple preference for utility apps)

---

## Iconography
- Style: Outline/stroke icons (Lucide React library)
- Weight: 1.5px stroke
- Size: 18px (nav, inline), 20px (buttons), 24px (page headers)
- Colour: inherits text colour
- Never filled icons — always outline/stroke only

---

## Do NOT
- Do not use glassmorphism, frosted glass, or backdrop-blur
- Do not use gradients on backgrounds, cards, or surfaces
- Do not use coloured shadows or glowing effects
- Do not use borders thicker than 1px
- Do not use pure white (#ffffff) — use zinc-50 (#fafafa)
- Do not use pure black (#000000) — use dark-bg (#0b1120)
- Do not use rounded corners larger than 16px (except pills)
- Do not animate layout changes
- Do not use icons with fill — stroke/outline only
