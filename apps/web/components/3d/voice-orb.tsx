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
    <div className={`relative h-full w-full ${className}`}>
      <DynamicScene isTyping={isTyping} />
    </div>
  );
}
