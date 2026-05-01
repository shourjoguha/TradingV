# UI components

`src/components/ui/*` — shadcn-style primitives, **handwritten** (not installed via `npx shadcn add`). All implement the **Neumorphism design system** — see "Theming" below.

## Currently shipped

`badge`, `button`, `calendar`, `card`, `date-picker`, `dialog`, `input`, `label`, `multi-select`, `popover`, `select`, `skeleton`, `sonner` (Toaster), `switch`, `table`, `textarea`, `toggle`, `toggle-group`. Also `BackendToggle` (composite, in `components/`).

### Floating surfaces — `popover`, `calendar`, `date-picker`, `multi-select`

- `popover.tsx` — Radix Popover wrapper. Content reads as an extruded card (`shadow-extruded`, `rounded-2xl`, `bg-card`) so floating UIs sit visually above the page surface (which is itself a same-color clay).
- `calendar.tsx` — `react-day-picker` v9 with neumorphic skin: violet extruded selected day, inset hover/focus on day buttons, inset chevron nav buttons. `optimizeDeps` and a single-React alias in [vite.config.ts](../../frontend/vite.config.ts) prevent the hoisted-React duplicate that triggers "Invalid hook call" with this lib.
- `date-picker.tsx` — composes `Popover` + `Calendar` + an Input-styled trigger button. Value/onChange take ISO `YYYY-MM-DD` strings (matches existing page state shape). UTC-stable: parses and emits via `Date.UTC` so anchor-mode date math doesn't drift across timezones.
- `multi-select.tsx` — searchable popover list with chip preview in the trigger (max 4 chips + "+N more" overflow), per-row checkmarks, "X selected" footer, Clear action. Trigger min-height grows with chip count; popover width matches trigger via `--radix-popover-trigger-width`.

## Pattern

Each is a Radix primitive + `cva` variants + `cn()` from `lib/utils.ts`.

```tsx
import * as Primitives from '@radix-ui/react-X'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'
```

## Theming — Neumorphism (Soft UI)

### Visual physics

Every interactive primitive maps to one of two states:
- **Extruded** — element raised off the page, dual shadows (light top-left, dark bottom-right). Used for resting state of buttons, cards, badges, and the BackendToggle dot's well.
- **Inset** — element pressed into the page, shadows reversed inward. Used for inputs, tables (container), tab containers, sidebar nav active state, and pressed buttons.

Hover lifts buttons + cards 1px and deepens the shadow. Active presses 0.5px and flips to inset. Focus shows a 2px violet ring offset by 2px on the page background.

### Tokens (defined in `tailwind.config.js`)

| Token | Value | Where |
|---|---|---|
| `bg-background` / `bg-card` | `#E0E5EC` (cool clay) | All surfaces. Same as page. |
| `text-foreground` | `#3D4852` (dark blue-grey) | Primary text. WCAG AAA on background. |
| `text-muted-foreground` | `#6B7280` (cool grey) | Secondary text. WCAG AA. |
| `bg-violet` / `text-violet` | `#6C63FF` (accent) | CTAs, focus rings, active nav text. |
| `bg-success` / `bg-success-bg` / `text-success-fg` | teal `#5FAFA8` family | Up/buy/positive |
| `bg-danger` / `bg-danger-bg` / `text-danger-fg` | coral `#E07A6F` family | Down/sell/negative |
| `bg-warning` / `bg-warning-bg` / `text-warning-fg` | amber `#D4A547` family | Drift alerts, caution |
| `shadow-extruded` | `9px 9px 16px rgb(163,177,198,0.6), -9px -9px 16px rgba(255,255,255,0.5)` | Cards |
| `shadow-extruded-hover` | bigger spread | Hover state |
| `shadow-extruded-sm` | 5px spread | Small buttons, badges |
| `shadow-inset` / `shadow-inset-deep` / `shadow-inset-sm` | inset variants | Inputs, tables, wells |
| `rounded-2xl` (16px), `rounded-3xl` (24px), `rounded-4xl` (32px) | extended | Buttons / cards / large containers |

### Fonts

`Plus Jakarta Sans` (display, weights 500-800) + `DM Sans` (body, weights 400-700), loaded from Google Fonts in `src/index.css`. Use `font-display` class for headlines (mostly automatic via `CardTitle`, `DialogTitle`, page headings).

### CSS vars + dark mode

CSS vars in `src/index.css` `:root`. **Dark mode dropped** — no `.dark` block, no `darkMode: 'class'` in Tailwind config. Anti-pattern: don't add it back without an explicit dark-neumorphism design.

`* { border-color: transparent }` in `index.css` makes bare `border` utilities visually invisible — neumorphism uses shadows for edges, not borders. If you need a visible border (rare), set `border-color` explicitly.

### Anti-patterns (don't do)

- Don't use `bg-white` for cards. Cards must match the page (`bg-background`).
- Don't add hex shadows. Use `shadow-extruded*` / `shadow-inset*` tokens.
- Don't use `rounded-md` or sharper. Minimum is `rounded-xl` (12px); prefer `rounded-2xl` (16px) for buttons, `rounded-3xl` (24px) for cards.
- Don't add bare `border` utilities expecting them to render — they're transparent globally.
- Don't use the Tailwind default font weights for body text. Headlines = `font-display font-bold` or `font-extrabold`; body = no font class needed (DM Sans default).

## Adding a new primitive

1. **shadcn CLI**: `npx shadcn@latest add <name>` then **rewrite** with neumorphic shadows + radii. The CLI default ships flat shadcn, not our look — it WILL look out of place if you skip the rewrite.
2. **Hand-write**: copy the existing primitive that's closest in interaction model and adapt. Rule: every interactive element gets `shadow-extruded-sm` or larger at rest, hover lifts + deepens, active = inset-sm.

## `cn()`

`clsx` + `tailwind-merge`. Use whenever combining classes, especially conditional. Lives in `lib/utils.ts`.

## Don't

- Don't import from `lucide-react` deep paths. Use top-level: `import { Foo } from 'lucide-react'`.
- Don't write inline `<style>` — Tailwind only.
- Don't add a new primitive without a use case in a page. Code dies in `ui/` fastest.
