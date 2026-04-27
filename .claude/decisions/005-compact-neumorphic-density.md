# ADR-005: Compact-neumorphic density (and 3 paired sub-decisions)

**Date**: 2026-04-27
**Status**: Accepted

## Context

The Neumorphism spec (ADR-004) prescribes airy spacing (`p-8`–`p-20`, `gap-12`, `py-32`) for marketing-style layouts. This app is data-dense — multi-column dashboards, dropdown-heavy forms, tables of jobs/predictions/trades. Pure-airy spec would push data 3× the current vertical space and shatter scannability.

Four sub-decisions made together to scope the redesign:

## Sub-decisions

### 1. Density: compact-neumorphic
**Picked**: Neumorphic shadows + radii + palette throughout, but data tables stay tight (`p-3`–`p-6`, `gap-3`–`gap-6`). Hero/sparse sections airy.
**Rejected**:
- Full-spec airy — breaks data tables.
- Hybrid (airy on Dashboard, dense on data) — risk of two visual languages within one app.

### 2. Semantic colors: kept (neumorphic-toned)
**Picked**: Muted teal `#5FAFA8` for positive/buy, muted coral `#E07A6F` for negative/sell, muted amber `#D4A547` for warning. Information density preserved on heatmap, P&L, status badges.
**Rejected**:
- Strict monochrome (violet accent only) — heatmap becomes shades of violet → grey, loses signal-readability.

### 3. Mobile nav: hamburger
**Picked**: Sidebar collapses to hamburger drawer below 768px; spec mandates touch-friendly targets (44px min).
**Rejected**:
- Defer (desktop-only) — ~1h saved but spec asks for it.

### 4. Dark mode: dropped
**Picked**: Light-only. No `darkMode: 'class'`, no `.dark` block in CSS. Single token set.
**Rejected**:
- Keep both — fork every component, dual maintenance.
- Build neumorphic dark variant — spec doesn't define it; design risk.

## Trigger to revisit

- Operator request for an airier look (e.g. presenting to others).
- Operator request for dark mode (would require designing dark-neumorphism).
- A11y review flags low-contrast somewhere.

## Files affected

Same set as [decisions/004-neumorphism-design-system.md](004-neumorphism-design-system.md).

## Cross-references

- [decisions/004-neumorphism-design-system.md](004-neumorphism-design-system.md) — parent decision
- [decisions/009-light-only-no-dark-mode.md](009-light-only-no-dark-mode.md) — dark-mode drop in detail
- [frontend/ui-components.md](../frontend/ui-components.md) — token reference
