/**
 * Unified Motion System Tokens — JKR AI Calling (Prompt B)
 * Single source of truth for physical animations, durations, easing curves,
 * springs, and choreography presets across marketing and operational screens.
 */

export const DURATION = {
  instant: 0.08,   // 80ms  - Button active down-press, micro-switches, tick marks
  fast: 0.14,      // 140ms - Tooltips, badge toggles, cursor specular highlight
  normal: 0.24,    // 240ms - Tab indicator sliding, card hover elevation, dropdowns
  moderate: 0.36,  // 360ms - Drawers, modals, route transitions, accordion expand
  slow: 0.60,      // 600ms - Hero entrance reveals, large container morphs
  ambient: 3.20,   // 3200ms- Continuous Voice Orb breathing, particle oscillations
} as const;

export const EASING = {
  // Apple / Linear deceleration curve
  standard: [0.2, 0.0, 0.0, 1.0] as const,
  // Snappy emphasized entrance for modals and hero cards
  emphasized: [0.16, 1.0, 0.3, 1.0] as const,
  // Quick, clean exit curve without lingering
  exit: [0.4, 0.0, 1.0, 1.0] as const,
} as const;

export const SPRING = {
  // Snappy response for navigation pills, active tabs, toggle switches
  snappy: { type: "spring", stiffness: 450, damping: 32, mass: 0.8 },
  // Smooth physical response for modal dialogs, slide-in drawers, card 3D tilt
  smooth: { type: "spring", stiffness: 220, damping: 28, mass: 1.0 },
  // Crisp bounciness for success checkmark morphs, notification badges, coin pops
  bouncy: { type: "spring", stiffness: 320, damping: 18, mass: 0.9 },
  // Gentle follower for cursor spotlights and magnetic CTA buttons
  magnetic: { type: "spring", stiffness: 140, damping: 16, mass: 0.6 },
} as const;

export const STAGGER = {
  tight: 0.035,   // 35ms  - Dense table rows, telemetry logs
  normal: 0.070,  // 70ms  - Form fields, dashboard KPI grid cards
  relaxed: 0.120, // 120ms - Marketing feature cards, pricing tiers
} as const;

import type { Variants } from "framer-motion";

export const MOTION_VARIANTS: Record<string, Variants> = {
  pageRoute: {
    initial: { opacity: 0, y: 10 },
    animate: { opacity: 1, y: 0, transition: { duration: DURATION.normal, ease: EASING.emphasized } },
    exit: { opacity: 0, y: -6, transition: { duration: DURATION.fast, ease: EASING.exit } },
  },
  fadeRise: {
    initial: { opacity: 0, y: 16 },
    animate: { opacity: 1, y: 0, transition: { duration: DURATION.moderate, ease: EASING.emphasized } },
    exit: { opacity: 0, y: 8, transition: { duration: DURATION.fast, ease: EASING.exit } },
  },
  cardLift: {
    rest: { y: 0, scale: 1, transition: { duration: DURATION.normal, ease: EASING.standard } },
    hover: { y: -4, scale: 1.01, transition: { duration: DURATION.normal, ease: EASING.emphasized } },
  },
  staggerContainer: {
    initial: {},
    animate: {
      transition: {
        staggerChildren: STAGGER.normal,
        delayChildren: 0.05,
      },
    },
  },
  staggerItem: {
    initial: { opacity: 0, y: 14 },
    animate: {
      opacity: 1,
      y: 0,
      transition: { duration: DURATION.moderate, ease: EASING.emphasized },
    },
  },
  popIn: {
    initial: { opacity: 0, scale: 0.92 },
    animate: { opacity: 1, scale: 1, transition: SPRING.bouncy },
    exit: { opacity: 0, scale: 0.94, transition: { duration: DURATION.fast, ease: EASING.exit } },
  },
  shakeError: {
    shake: {
      x: [0, -6, 6, -4, 4, -2, 2, 0],
      transition: { duration: 0.32, ease: EASING.standard },
    },
    default: { x: 0 },
  },
};
