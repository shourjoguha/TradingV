# ADR-009: Light-only frontend; no dark mode

**Date**: 2026-04-27 (during Neumorphism redesign)
**Status**: Accepted

## Context

Original frontend shipped with `class="dark"` on `<html>` and a full dark-mode CSS variable set. The Neumorphism design system (ADR-004) is fundamentally light-only by spec — the `#E0E5EC` "cool clay" base + dual-shadow physics don't translate cleanly to dark.

## Options considered

- **A · Drop dark entirely** — single token set. Spec is light-only. Cleanest.
- **B · Keep both** — neumorphic light + existing dark. Fork every component; dual maintenance.
- **C · Build neumorphic dark variant** — pure neumorphism for both modes. Spec doesn't define dark; we'd be designing it (e.g. `#1F2329` base, same shadow physics). Adds ~3h + design risk.

## Decision

**Drop dark entirely.** Reasons:
- Spec mandates light-only.
- Single user; no second persona who prefers dark.
- Single token set = less code, less divergence over time.
- Add later if needed without retroactive cost (each component would gain a `.dark` variant).

## Trade-offs accepted

- Operators who prefer dark UIs in their general environment lose the toggle.
- Light backgrounds on OLED screens consume more power (negligible for desktop use).

## Trigger to revisit

- Operator request for dark mode.
- Onboarding a second user who needs dark.
- Display environment shifts (e.g. presenting in a dark room, eye strain).

## Files affected

- `frontend/tailwind.config.js` — removed `darkMode: 'class'`.
- `frontend/src/index.css` — removed `.dark { ... }` block.
- `frontend/index.html` — removed `class="dark"` from `<html>`.
- `* { border-color: transparent }` global rule — neumorphism uses shadows, not borders.

## Cross-references

- [decisions/004-neumorphism-design-system.md](004-neumorphism-design-system.md) — parent design choice
- [decisions/005-compact-neumorphic-density.md](005-compact-neumorphic-density.md) — sub-decision #4
- [frontend/ui-components.md](../frontend/ui-components.md) — anti-pattern list mentions "don't add dark mode back"
