# UI components

`src/components/ui/*` — shadcn-style primitives, **handwritten** (not installed via `npx shadcn add`). Magic Patterns abstracts these as design-system tokens; we wrote concrete React components.

## Currently shipped

`badge`, `button`, `card`, `dialog`, `input`, `label`, `select`, `skeleton`, `sonner` (Toaster), `switch`, `table`, `textarea`, `toggle`, `toggle-group`.

## Pattern

Each is a Radix primitive + `cva` variants + `cn()` from `lib/utils.ts`. Standard shadcn copy — if you've seen one shadcn project, you've seen all of them.

```tsx
import * as Primitives from '@radix-ui/react-X'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'
```

## Adding a new primitive

Two paths:

1. **shadcn CLI**: `npx shadcn@latest add <name>`. Reads `components.json` (already configured), drops file in `src/components/ui/`. Watch out — it may overwrite handwritten ones.
2. **Hand-write**: copy the official shadcn snippet from https://ui.shadcn.com/docs/components/<name>. Same pattern as existing files.

Either way: don't use the design-system abstraction Magic Patterns generates (`components/ui/badge` with no extension is just a stub).

## Theming

CSS vars in `src/index.css`. Dark mode is default (`<html class="dark">` set in `index.html` and `main.tsx`). `tailwind.config.js` maps `bg-background` etc. to those vars via `hsl(var(--X))`.

To change theme: edit `src/index.css` `:root` and `.dark` blocks. Tokens follow standard shadcn naming (`--background`, `--foreground`, `--primary`, etc.).

## `cn()`

`clsx` + `tailwind-merge`. Use it whenever combining classes, especially conditional. Lives in `lib/utils.ts`.

## Don't

- Don't import from `lucide-react` deep paths (`lucide-react/dist/...`). Use top-level: `import { Foo } from 'lucide-react'`.
- Don't write inline `<style>` — Tailwind everywhere.
- Don't add a new primitive without a use case in a page. Code dies in `ui/` faster than anywhere else.
