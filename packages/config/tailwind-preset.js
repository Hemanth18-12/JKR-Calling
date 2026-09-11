/**
 * Shared Tailwind design tokens — JKR AI Calling.
 * Palette: Deep true-black (#0A0A0A) base, charcoal cards (#161616),
 * Vivid Yellow (#FFD400) brand, and Amber (#FF9F1C) live-voice/real-time.
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
        "voice-live": "#FF9F1C",   /* Vivid Amber — live call / real-time */
        "voice-brand": "#FFD400",  /* Vibrant Yellow — brand / action */
        "voice-outcome": "#FFAA00", /* Warm Yellow-Amber — success / outcome */
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
          "linear-gradient(135deg, #FFD400 0%, #FFA000 100%)",
        "gradient-live":
          "linear-gradient(135deg, #FF9F1C 0%, #E67E00 100%)",
        "gradient-hero":
          "radial-gradient(ellipse at 60% 30%, rgba(255,212,0,0.12) 0%, rgba(255,159,28,0.06) 55%, transparent 80%)",
        "gradient-mesh":
          "radial-gradient(at 20% 80%, rgba(255,212,0,0.08) 0px, transparent 50%), radial-gradient(at 80% 20%, rgba(255,159,28,0.05) 0px, transparent 50%)",
        "gradient-cta":
          "linear-gradient(135deg, #FFD400 0%, #FFA000 100%)",
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
          "0%": { transform: "scale(0.95)", opacity: "0.85" },
          "50%": { transform: "scale(1.2)", opacity: "0.2" },
          "100%": { transform: "scale(0.95)", opacity: "0.85" },
        },
        "float-glow": {
          "0%, 100%": { transform: "translateY(0px)", opacity: "0.7" },
          "50%": { transform: "translateY(-8px)", opacity: "1" },
        },
        "fade-rise": {
          "0%": { opacity: "0", transform: "translateY(12px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      boxShadow: {
        "primary-glow": "0 0 24px rgba(255, 212, 0, 0.35)",
        "live-glow": "0 0 20px rgba(255, 159, 28, 0.45)",
        "card-raised": "0 8px 32px rgba(0, 0, 0, 0.6), 0 0 0 1px rgba(255, 212, 0, 0.08)",
        "card-3d": "0 10px 30px -5px rgba(0, 0, 0, 0.8), 0 0 0 1px rgba(255, 255, 255, 0.05)",
        "card-3d-hover": "0 16px 36px -4px rgba(0, 0, 0, 0.9), 0 0 25px rgba(255, 212, 0, 0.2)",
      },
    },
  },
  plugins: [],
};
