# ADR-004: Neumorphism (Soft UI) design system

**Date**: 2026-04-27
**Status**: Accepted

## Context

Frontend shipped on CF Pages with the original dark, generic shadcn-default look. Operator wanted a more distinctive, tactile aesthetic. The Neumorphism (Soft UI) design system was provided as a directional spec — directional because it's data-dense at heart and the spec assumes airier marketing-style layouts.

## Options considered

- **A · Neumorphism (Soft UI)** — light-only, monochromatic cool grey, dual opposing RGBA shadows, hyper-rounded corners, Plus Jakarta + DM Sans fonts.
- **B · Refined dark with accent palette** — keep dark, polish; lower aesthetic risk.
- **C · Other system (Glassmorphism, Brutalism, Material 3)** — not evaluated; Neumorphism was operator's pick.

## Decision

**Neumorphism, applied pragmatically.** Locked four sub-decisions that shape the implementation (each is its own ADR-005 covering the density/colors/dark mode/mobile-nav choices). The core: monochromatic `#E0E5EC` base, dual shadows, rounded-2xl/3xl, no dark mode, no hex shadows, no borders.

## Trigger to revisit

- Operator burns out on the look (subjective; revisit on operator request).
- Performance: heavy box-shadows × many small elements hurts scroll perf on mobile.
- Need for high-contrast (a11y) mode that pure neumorphism can't deliver.

## Files affected

- `frontend/tailwind.config.js` (palette, shadow tokens, radii, fonts, drop dark mode)
- `frontend/src/index.css` (CSS vars, body styles, font imports)
- `frontend/index.html` (drop `class="dark"`)
- `frontend/src/components/ui/*` (16 primitives rewritten)
- `frontend/src/components/{Layout,BackendToggle}.tsx`
- `frontend/src/pages/*.tsx` (page-level cleanup; charts theming)

## Cross-references

- [decisions/005-compact-neumorphic-density.md](005-compact-neumorphic-density.md) — the four sub-decisions
- [frontend/ui-components.md](../frontend/ui-components.md) — design system token reference
- [decisions/009-light-only-no-dark-mode.md](009-light-only-no-dark-mode.md) — dark-mode drop
