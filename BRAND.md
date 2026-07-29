# HALI Brand Guide

Single source of truth for the HALI landing site and any future design work.
Direction B — technical, steel dark, purple as a data accent.

## What HALI is

HALI is a hyper-local early warning system for the eight IGAD member states.
It ingests satellite and hazard data from five sources on a daily schedule,
normalises it through a PostGIS spatial database, translates each alert into
10 languages with a multi-model AI ensemble, and generates livelihood-specific
action guidance. Alerts reach people over USSD, WhatsApp and an offline-capable
web app. There is no account, no subscription and no app install.

## Voice

- Direct, technical, unembellished. We describe what the system does, not
  how excited we are about it.
- Sentence case everywhere — headings, buttons, labels. Never Title Case.
- No exclamation marks. No "leverage", "seamless", "unlock", "empower",
  "revolutionize", "cutting-edge", "game-changing".
- No em dashes in body copy. Use periods or commas. Short sentences.
- Numbers over adjectives: "10 languages" not "many languages";
  "5 satellite sources" not "lots of data".
- Every number on the site must be traceable to the repository or the
  technical specs. We do not publish statistics we cannot source.
- Active voice, verb first in CTAs: "Open the app", not "Get Started Now!"
- Complementary, never competitive, about ICPAC and other regional systems.
  We describe what HALI adds. We do not describe what anyone else lacks.

## What we explicitly avoid (read before designing anything)

- Purple-to-indigo gradient hero backgrounds — the single most common
  "AI generated this" tell in 2025-2026 web design.
- Gradient text on headlines.
- Glassmorphism / frosted-glass panels.
- Glow or neon effects on dark backgrounds.
- Pill-shaped badges scattered everywhere as decoration.
- The generic "3 feature cards in a row with an icon on top" pattern
  used without genuine content differentiation.
- Stock photography of "diverse people smiling at phones."
- Oversized hero headline + vague subhead + single centered CTA button
  with nothing else on screen.
- Emoji anywhere in UI copy or headings.

## Color

Primary: purple, used **sparingly** as a single accent — never as a
background gradient, never as more than ~10% of any given screen's ink.
It marks: the wordmark, data figures, the one primary CTA state, active
nav underline. It does not paint hero backgrounds or fill icon badges.

| Token | Hex | Use |
|---|---|---|
| purple-100 | #CECBF6 | rare — hover tint only |
| purple-400 | #7F77DD | data figures, links, active states |
| purple-600 | #534AB7 | primary button fill (light mode) |
| purple-900 | #26215C | text-on-purple-tint, dark-mode wordmark |

Neutral base carries the page. Light mode: warm off-white `#FAF9F6`
background — not pure white, not gray. Dark mode: steel-blue-black
`#0e1824`, matching the existing HALI app dark mode. Never `#000`.

Steel neutrals are the app's existing slate ramp, reused verbatim from
`apps/frontend/src/styles.css` so the two sites read as one family.

Severity colors (reused from the app, do not invent new ones):
red `#dc2626` / orange `#ea580c` / green `#16a34a`.

## Typography

Inter throughout. Two weights only: 400 body, 500 for headings and
emphasis. Never 600/700 — reads heavy against the restrained palette.
Headline sizes: h1 28-32px, h2 20px, h3 16px. Body 15-16px, line-height 1.6.

Numerals in data figures use `font-variant-numeric: tabular-nums` so
columns of statistics align.

## Components

Reuse shadcn/ui primitives already installed in `apps/frontend`
(Button, Card, Badge, Separator) — import the same visual language,
do not reinvent buttons or cards from scratch. Astro can consume React
components directly as islands; use this to avoid re-styling from zero.

## Iconography

Lucide icons only, outline style, 20-24px, single color
(`var(--text-secondary)` or purple-400 for emphasis). No icon in a filled
colored circle badge — that reads as decoration, not information.

## Layout rules

- No section is "headline + vague copy + button" alone — every section
  has one specific, falsifiable claim (a number, a named technology,
  a real screenshot) next to the prose.
- Whitespace does the separating — avoid boxed cards for every section;
  reserve bordered cards for genuinely bounded content (a stat, a repo link).
- Maximum content width 720px for prose sections, wider for diagrams/screens.
- Hairline rules (1px, `--border`) separate sections. No drop shadows on
  layout containers.

## Source of truth for facts

| Claim | Where it is verified |
|---|---|
| 10 languages | `packages/types/src/index.ts` — `Language` union |
| 7 livelihoods | `packages/types/src/index.ts` — `Livelihood` union |
| 10 hazard types | `packages/types/src/index.ts` — `HazardType` union |
| 8 IGAD countries | `infra/railway.md` — seed ISO2 codes |
| 5 ingestion sources | `HALI_FEATURES_TECHNICAL_SPECS.md` §2.2 |
| AI ensemble models | `.env.example` — `AI_PRIMARY_MODEL`, Gemini, Groq |
| Capability matrix | `HALI_FEATURES_TECHNICAL_SPECS.md` §13.1 |

If a number is not in that table, it does not go on the site until a
source exists for it.
