/**
 * Shared Tailwind design tokens — JKR AI Calling v2.
 * New palette: Deep charcoal-indigo base, Electric Violet brand,
 * Cyan Teal live-voice, Marigold Amber outcomes.
 */
/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: ["class"],
  theme: {
    extend: {
      colors: {
        background: "hsl(var(--background))",
        surface: "hsl(var(--surface))",
        "surface-raised": "hsl(var(--surface-raised))",
        border: "hsl(var(--border))",
        foreground: "hsl(var(--foreground))",
        muted: "hsl(var(--muted))",
        "muted-foreground": "hsl(var(--muted-foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        success: "hsl(var(--success))",
        warning: "hsl(var(--warning))",
        danger: "hsl(var(--danger))",
        ring: "hsl(var(--ring))",
        /* Named semantic tokens for the 3-accent system */
        "voice-live": "#2DD4BF",   /* Cyan Teal — live call / real-time */
        "voice-brand": "#7C5CFF", /* Electric Violet — brand / action */
        "voice-outcome": "#FFA94D", /* Marigold Amber — success / outcome */
      },
      borderRadius: {
        xl: "1rem",
        lg: "0.75rem",
        md: "0.5rem",
        sm: "0.375rem",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui", "sans-serif"],
        display: ["var(--font-display)", "var(--font-sans)", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      backgroundImage: {
        "gradient-brand":
          "linear-gradient(135deg, #7C5CFF 0%, #5B3FE4 100%)",
        "gradient-live":
          "linear-gradient(135deg, #2DD4BF 0%, #1A9E8C 100%)",
        "gradient-hero":
          "radial-gradient(ellipse at 60% 30%, rgba(124,92,255,0.18) 0%, rgba(45,212,191,0.10) 55%, transparent 80%)",
        "gradient-mesh":
          "radial-gradient(at 20% 80%, rgba(124,92,255,0.12) 0px, transparent 50%), radial-gradient(at 80% 20%, rgba(45,212,191,0.08) 0px, transparent 50%)",
        "gradient-cta":
          "linear-gradient(135deg, hsl(var(--primary)) 0%, #5B3FE4 100%)",
      },
      animation: {
        "wave-1": "wave-bounce 1.1s ease-in-out infinite",
        "wave-2": "wave-bounce 0.85s ease-in-out infinite 0.15s",
        "wave-3": "wave-bounce 1.3s ease-in-out infinite 0.3s",
        "wave-4": "wave-bounce 0.95s ease-in-out infinite 0.45s",
        "pulse-ring": "pulse-ring 2s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "float-glow": "float-glow 4s ease-in-out infinite",
        "fade-rise": "fade-rise 0.5s ease-out forwards",
      },
      keyframes: {
        "wave-bounce": {
          "0%, 100%": { height: "6px" },
          "50%": { height: "24px" },
        },
        "pulse-ring": {
          "0%": { transform: "scale(0.95)", opacity: "0.8" },
          "50%": { transform: "scale(1.2)", opacity: "0.2" },
          "100%": { transform: "scale(0.95)", opacity: "0.8" },
        },
        "float-glow": {
          "0%, 100%": { transform: "translateY(0px)", opacity: "0.6" },
          "50%": { transform: "translateY(-8px)", opacity: "0.9" },
        },
        "fade-rise": {
          "0%": { opacity: "0", transform: "translateY(12px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      boxShadow: {
        "primary-glow": "0 0 20px rgba(124, 92, 255, 0.25)",
        "live-glow": "0 0 16px rgba(45, 212, 191, 0.35)",
        "card-raised": "0 4px 24px rgba(0, 0, 0, 0.35)",
      },
    },
  },
  plugins: [],
};
