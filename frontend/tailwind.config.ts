import type { Config } from "tailwindcss";

/**
 * Tailwind theme is derived from the design system in docs/DESIGN_SYSTEM.md.
 * Tokens flow: CSS variables (globals.css) → Tailwind utilities (here) →
 * component classes. Components should reference semantic utilities
 * (`bg-primary`, `text-success`), never raw hex.
 */
const config: Config = {
  darkMode: ["class"],
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    container: {
      center: true,
      // 0.75rem (12px) on phones gives data-dense tables more room without
      // letting text touch the viewport edge; 1rem/1.5rem at larger
      // breakpoints stays comfortable.
      padding: { DEFAULT: "0.75rem", sm: "1rem", lg: "1.5rem" },
      screens: { "2xl": "1280px" },
    },
    screens: {
      sm: "640px",
      md: "768px",
      lg: "1024px",
      xl: "1280px",
      "2xl": "1536px",
    },
    extend: {
      fontFamily: {
        sans: ["var(--font-sans)"],
        mono: ["var(--font-mono)"],
      },
      fontSize: {
        // Modular scale 1.200 — see §2.2 of DESIGN_SYSTEM.md
        xs: ["0.75rem", { lineHeight: "1.4" }],
        sm: ["0.875rem", { lineHeight: "1.45" }],
        base: ["1rem", { lineHeight: "1.55" }],
        lg: ["1.125rem", { lineHeight: "1.5" }],
        xl: ["1.25rem", { lineHeight: "1.4" }],
        "2xl": ["1.5rem", { lineHeight: "1.3" }],
        "3xl": ["1.875rem", { lineHeight: "1.2" }],
        "4xl": ["2.25rem", { lineHeight: "1.1" }],
      },
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        // Honour accent — citizen-facing achievements only
        honour: {
          DEFAULT: "hsl(var(--brand-accent))",
          foreground: "hsl(var(--brand-accent-foreground))",
        },
        // Ministry / admin chrome
        deep: {
          DEFAULT: "hsl(var(--brand-deep))",
          foreground: "hsl(var(--brand-deep-foreground))",
        },
        // Semantic state — pair with an icon, never colour-alone
        success: {
          DEFAULT: "hsl(var(--state-success))",
          foreground: "hsl(var(--state-success-100))",
          soft: "hsl(var(--state-success-100))",
        },
        info: {
          DEFAULT: "hsl(var(--state-info))",
          foreground: "hsl(var(--state-info-100))",
          soft: "hsl(var(--state-info-100))",
        },
        warning: {
          DEFAULT: "hsl(var(--state-warning))",
          foreground: "hsl(var(--state-warning-100))",
          soft: "hsl(var(--state-warning-100))",
        },
        danger: {
          DEFAULT: "hsl(var(--state-danger))",
          foreground: "hsl(var(--state-danger-100))",
          soft: "hsl(var(--state-danger-100))",
        },
        neutral: {
          DEFAULT: "hsl(var(--state-neutral))",
        },
      },
      borderRadius: {
        sm: "calc(var(--radius) - 4px)",
        md: "calc(var(--radius) - 2px)",
        lg: "var(--radius)",
        xl: "calc(var(--radius) + 4px)",
      },
      spacing: {
        // 4px base — every multiple-of-4 is already covered by Tailwind's
        // default scale (gap-1=4, gap-2=8, gap-4=16, …). We add only the
        // semantic aliases used by the layout shells.
        page: "2.5rem",       // --space-10 — worker page top padding
        section: "2rem",      // --space-8 — between dashboard sections
      },
      boxShadow: {
        1: "var(--shadow-1)",
        2: "var(--shadow-2)",
      },
      minHeight: {
        // WCAG 2.5.5 — clinicians wear gloves
        touch: "44px",
      },
      minWidth: {
        touch: "44px",
      },
      maxWidth: {
        prose: "70ch",
      },
    },
  },
  // eslint-disable-next-line @typescript-eslint/no-require-imports -- Tailwind plugins ship as CJS; require is the documented loader pattern.
  plugins: [require("tailwindcss-animate")],
};

export default config;
