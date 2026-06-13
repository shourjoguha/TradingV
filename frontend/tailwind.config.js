import animate from 'tailwindcss-animate'

/** @type {import('tailwindcss').Config} */
export default {
  // Dark mode dropped: neumorphism is light-only by spec.
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    container: {
      center: true,
      padding: '1rem',
      screens: { '2xl': '1400px' },
    },
    extend: {
      colors: {
        // CSS-var-bound (compat with existing shadcn primitives) — all
        // values point at the same neumorphic palette so legacy class
        // names like `bg-card`, `text-muted-foreground` still resolve
        // sensibly.
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        card: {
          DEFAULT: 'hsl(var(--card))',
          foreground: 'hsl(var(--card-foreground))',
        },
        popover: {
          DEFAULT: 'hsl(var(--popover))',
          foreground: 'hsl(var(--popover-foreground))',
        },
        primary: {
          DEFAULT: 'hsl(var(--primary))',
          foreground: 'hsl(var(--primary-foreground))',
          // Hover + active variants for the graphite-ink primary (2026-05-17
          // recast — replaces the previous vibrant violet). Use as
          // `bg-primary-light` for hover surface fills and inactive-tab text,
          // `bg-primary-active` for pressed CTAs + focused input borders.
          light: '#4A5C73',
          active: '#1C2838',
        },
        secondary: {
          DEFAULT: 'hsl(var(--secondary))',
          foreground: 'hsl(var(--secondary-foreground))',
        },
        muted: {
          DEFAULT: 'hsl(var(--muted))',
          foreground: 'hsl(var(--muted-foreground))',
        },
        accent: {
          DEFAULT: 'hsl(var(--accent))',
          foreground: 'hsl(var(--accent-foreground))',
        },
        destructive: {
          DEFAULT: 'hsl(var(--destructive))',
          foreground: 'hsl(var(--destructive-foreground))',
        },
        border: 'hsl(var(--border))',
        input: 'hsl(var(--input))',
        ring: 'hsl(var(--ring))',
        chart: {
          1: 'hsl(var(--chart-1))',
          2: 'hsl(var(--chart-2))',
          3: 'hsl(var(--chart-3))',
          4: 'hsl(var(--chart-4))',
          5: 'hsl(var(--chart-5))',
        },
        // Neumorphic-toned semantic palette. Used directly as
        // bg-success / text-danger / etc. in pages where information
        // density needs color (P&L, hit-rate heatmap, status badges).
        success: {
          DEFAULT: '#5FAFA8',
          fg: '#1F4E4A',
          bg: '#D8EBE9',
        },
        danger: {
          DEFAULT: '#E07A6F',
          fg: '#5C2A24',
          bg: '#F4D9D5',
        },
        warning: {
          DEFAULT: '#D4A547',
          fg: '#574115',
          bg: '#F5E7C5',
        },
        // (Previously a vibrant violet `#6C63FF` lived here as the
        // primary accent. Recast to graphite ink 2026-05-17 — see ADR
        // / decisions in roadmap-shipped retro. Use `primary` /
        // `primary-light` / `primary-active` instead.)
        teal: {
          DEFAULT: '#38B2AC',
        },
        // Matte-bold identity palette (2026-05-17 council).
        // Identity = "what kind of content is this" (regime / narrative
        // / ambient). Orthogonal to the semantic trio above (success
        // /danger/warning encode direction-of-state). Use as 4px left-
        // bars, dots, badge fills, sparkline strokes — NEVER as card
        // backgrounds. See .claude/frontend/ui-components.md "Color
        // taxonomy" for the rules of engagement.
        identity: {
          inflation: '#C58A3D',  // burnt ochre — Macro/Inflation regime
          growth:    '#3F7A6E',  // forest-teal — Macro/Growth + realized-positive (closed wins)
          liquidity: '#4A6FA5',  // slate-blue  — Macro/Liquidity + Yield curve
          stress:    '#B0533C',  // brick       — Macro/Stress + invalidated-thesis tier
          narrative: '#7A5AA8',  // plum        — Theses + Research-answer chrome + TV-Context
          ambient:   '#5C7A8C',  // steel       — sparkline gridlines + Today's "curious" card
        },
        // Motion-only wash colors. Used to lerp card-bg during
        // disposition POST 200 (success/snooze/dismiss) and the
        // K-logo ambient-attention ring. Saturation is intentionally
        // low so washes feel like light, not paint.
        wash: {
          success: 'hsl(158 38% 84%)',
          snooze:  'hsl(38 45% 86%)',
          dismiss: 'hsl(220 6% 82%)',
        },
      },
      borderRadius: {
        // Existing radius tokens kept for compat. Extend with the
        // neumorphic-friendly aliases.
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 2px)',
        sm: 'calc(var(--radius) - 4px)',
        '2xl': '16px',
        '3xl': '24px',
        '4xl': '32px',
      },
      boxShadow: {
        // Neumorphic shadow tokens. Use as shadow-extruded etc.
        extruded: '9px 9px 16px rgb(163 177 198 / 0.6), -9px -9px 16px rgba(255 255 255 / 0.5)',
        'extruded-hover': '12px 12px 20px rgb(163 177 198 / 0.7), -12px -12px 20px rgba(255 255 255 / 0.6)',
        'extruded-sm': '5px 5px 10px rgb(163 177 198 / 0.6), -5px -5px 10px rgba(255 255 255 / 0.5)',
        inset: 'inset 6px 6px 10px rgb(163 177 198 / 0.6), inset -6px -6px 10px rgba(255 255 255 / 0.5)',
        'inset-deep': 'inset 10px 10px 20px rgb(163 177 198 / 0.7), inset -10px -10px 20px rgba(255 255 255 / 0.6)',
        'inset-sm': 'inset 3px 3px 6px rgb(163 177 198 / 0.6), inset -3px -3px 6px rgba(255 255 255 / 0.5)',
        // Ambient-attention ring for the K-logo when inbox > 0.
        // Used by the .animate-attention-pulse keyframe in index.css.
        'attention-ring': '0 0 0 1px hsl(213 28% 25% / 0.18)',
      },
      fontFamily: {
        display: ['"Plus Jakarta Sans"', 'system-ui', 'sans-serif'],
        sans: ['"DM Sans"', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
      keyframes: {
        float: {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-8px)' },
        },
        'accordion-down': {
          from: { height: '0' },
          to: { height: 'var(--radix-accordion-content-height)' },
        },
        'accordion-up': {
          from: { height: 'var(--radix-accordion-content-height)' },
          to: { height: '0' },
        },
        // K-logo breathing ring (Phase 6 color taxonomy). Slow 3.2s cycle,
        // peripheral-vision channel — felt, not seen.
        'attention-pulse': {
          '0%, 100%': { boxShadow: '0 0 0 1px hsl(213 28% 25% / 0.10)' },
          '50%':      { boxShadow: '0 0 0 1px hsl(213 28% 25% / 0.22)' },
        },
        // Disposition wash (Phase 5). Overlay div mounts on POST 200,
        // backgroundColor lerps to wash color at mid-point and back to
        // transparent. Three variants — success / snooze / dismiss.
        'disposition-wash-success': {
          '0%, 100%': { backgroundColor: 'transparent' },
          '50%':      { backgroundColor: 'hsl(158 38% 84%)' },
        },
        'disposition-wash-snooze': {
          '0%, 100%': { backgroundColor: 'transparent' },
          '50%':      { backgroundColor: 'hsl(38 45% 86%)' },
        },
        'disposition-wash-dismiss': {
          '0%, 100%': { backgroundColor: 'transparent' },
          '50%':      { backgroundColor: 'hsl(220 6% 82%)' },
        },
      },
      animation: {
        float: 'float 3s ease-in-out infinite',
        'accordion-down': 'accordion-down 0.18s ease-out',
        'accordion-up': 'accordion-up 0.18s ease-out',
        'attention-pulse': 'attention-pulse 3.2s ease-in-out infinite',
        'disposition-wash-success': 'disposition-wash-success 320ms ease-out',
        'disposition-wash-snooze':  'disposition-wash-snooze 320ms ease-out',
        'disposition-wash-dismiss': 'disposition-wash-dismiss 320ms ease-out',
      },
    },
  },
  plugins: [animate],
}
