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
        mono: ["var(--font-mono)", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      backgroundImage: {
        "gradient-brand": "linear-gradient(180deg, #FFD400 0%, #F5C800 100%)",
        "gradient-live": "linear-gradient(180deg, #F59E0B 0%, #D97706 100%)",
      },
      animation: {
        "wave-1": "wave-bounce 1.1s ease-in-out infinite",
        "wave-2": "wave-bounce 0.85s ease-in-out infinite 0.15s",
        "wave-3": "wave-bounce 1.3s ease-in-out infinite 0.3s",
        "wave-4": "wave-bounce 0.95s ease-in-out infinite 0.45s",
        "pulse-subtle": "pulse-subtle 2s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "fade-rise": "fade-rise 0.35s ease-out forwards",
      },
      keyframes: {
        "wave-bounce": {
          "0%, 100%": { height: "4px" },
          "50%": { height: "20px" },
        },
        "pulse-subtle": {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.4" },
        },
        "fade-rise": {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      boxShadow: {
        "subtle": "0 1px 2px 0 rgba(0, 0, 0, 0.4)",
        "card": "0 1px 3px 0 rgba(0, 0, 0, 0.5), 0 1px 2px -1px rgba(0, 0, 0, 0.5)",
        "card-elevated": "0 4px 16px -2px rgba(0, 0, 0, 0.6)",
        "dropdown": "0 10px 25px -5px rgba(0, 0, 0, 0.7), 0 8px 10px -6px rgba(0, 0, 0, 0.7)",
      },
    },
  },
  plugins: [],
};
