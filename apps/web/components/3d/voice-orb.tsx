"use client";

import dynamic from "next/dynamic";
import * as React from "react";

import { VoiceOrbFallback } from "./voice-orb-fallback";

const DynamicScene = dynamic(() => import("./voice-orb-scene"), {
  ssr: false,
  loading: () => <VoiceOrbFallback />,
});

interface VoiceOrbProps {
  isTyping?: boolean;
  className?: string;
}

class OrbErrorBoundary extends React.Component<
  { fallback: React.ReactNode; children: React.ReactNode },
  { hasError: boolean }
> {
  constructor(props: any) {
    super(props);
    this.state = { hasError: false };
  }
  static getDerivedStateFromError() {
    return { hasError: true };
  }
  componentDidCatch(error: any) {
    // Gracefully catch any Three.js / WebGL / driver exceptions
    console.warn("3D scene error, using CSS 3D orb fallback:", error);
  }
  render() {
    if (this.state.hasError) {
      return this.props.fallback;
    }
    return this.props.children;
  }
}

export function VoiceOrb({ isTyping = false, className = "" }: VoiceOrbProps) {
  const [reduceMotion, setReduceMotion] = React.useState(false);
  const [mounted, setMounted] = React.useState(false);

  React.useEffect(() => {
    setMounted(true);
    const mediaQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduceMotion(mediaQuery.matches);

    const handler = (e: MediaQueryListEvent) => setReduceMotion(e.matches);
    mediaQuery.addEventListener("change", handler);
    return () => mediaQuery.removeEventListener("change", handler);
  }, []);

  if (!mounted || reduceMotion) {
    return <VoiceOrbFallback isTyping={isTyping} className={className} />;
  }

  return (
    <OrbErrorBoundary fallback={<VoiceOrbFallback isTyping={isTyping} className={className} />}>
      <VoiceOrbFallback isTyping={isTyping} className={className} />
    </OrbErrorBoundary>
  );
}
