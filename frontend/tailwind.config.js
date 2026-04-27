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
        // Accent shorthand for direct use (the design-system spec
        // names these). Same as primary above; here for clarity.
        violet: {
          DEFAULT: '#6C63FF',
          light: '#8B84FF',
        },
        teal: {
          DEFAULT: '#38B2AC',
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
      },
      animation: {
        float: 'float 3s ease-in-out infinite',
      },
    },
  },
  plugins: [animate],
}
