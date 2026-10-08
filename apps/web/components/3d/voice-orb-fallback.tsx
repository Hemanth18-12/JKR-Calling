"use client";

import * as React from "react";

interface VoiceOrbFallbackProps {
  isTyping?: boolean;
  className?: string;
}

export function VoiceOrbFallback({ isTyping = false, className = "" }: VoiceOrbFallbackProps) {
  return (
    <div className={`relative flex h-full w-full items-center justify-center overflow-hidden ${className}`}>
      {/* Background ambient radial glow */}
      <div className="pointer-events-none absolute h-96 w-96 rounded-full bg-primary/15 blur-3xl" />
      <div className="pointer-events-none absolute h-64 w-64 rounded-full bg-secondary/10 blur-2xl" />

      {/* Orbiting Language Glyphs */}
      <div className="pointer-events-none absolute inset-0 flex items-center justify-center z-10">
        <div className="relative flex items-center justify-center h-48 w-48">
          <div className="absolute -top-14 animate-float-glow rounded-full border border-primary/40 bg-surface/90 px-3 py-1 text-[11px] font-bold text-primary backdrop-blur-md shadow-md shadow-primary/25 flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse" />
            <span>నమస్తే (Telugu)</span>
          </div>
          <div className="absolute -right-16 top-14 animate-float-glow rounded-full border border-secondary/40 bg-surface/90 px-3 py-1 text-[11px] font-bold text-amber-400 backdrop-blur-md shadow-md shadow-secondary/25 [animation-delay:1.5s] flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-amber-400 animate-pulse" />
            <span>नमस्ते (Hindi)</span>
          </div>
          <div className="absolute -left-16 top-14 animate-float-glow rounded-full border border-border/80 bg-surface/90 px-3 py-1 text-[11px] font-bold text-foreground backdrop-blur-md shadow-md [animation-delay:0.8s] flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-white/80 animate-pulse" />
            <span>Hello (English)</span>
          </div>
        </div>
      </div>

      {/* Concentric Pulse Rings */}
      <div className={`absolute h-72 w-72 rounded-full border border-primary/20 transition-transform duration-300 ${isTyping ? "scale-110 border-primary/40" : "animate-pulse-ring"}`} />
      <div className={`absolute h-56 w-56 rounded-full border border-primary/30 transition-transform duration-300 [animation-delay:0.4s] ${isTyping ? "scale-105 border-primary/50" : "animate-pulse-ring"}`} />

      {/* Central Glass Orb */}
      <div className={`relative flex h-40 w-40 items-center justify-center rounded-full border border-primary/40 bg-gradient-to-br from-primary/30 via-surface to-background p-1 shadow-2xl backdrop-blur-xl transition-all duration-300 ${isTyping ? "scale-105 shadow-primary/40" : "shadow-primary/20"}`}>
        <div className="flex h-full w-full items-center justify-center rounded-full bg-gradient-to-tr from-primary/20 to-transparent">
          {/* Internal Pulsing Voice Core */}
          <div className={`h-20 w-20 rounded-full bg-gradient-to-br from-primary to-[#FFA000] shadow-lg shadow-primary/50 transition-all duration-300 ${isTyping ? "scale-125 animate-pulse" : "animate-pulse"}`} />
        </div>
      </div>

      {/* Dynamic Soundwave Bars at bottom of Orb */}
      <div className="absolute bottom-16 flex items-center gap-1.5">
        <span className={`w-1 rounded-full bg-primary ${isTyping ? "h-6 animate-wave-1" : "h-3 animate-wave-1"}`} />
        <span className={`w-1 rounded-full bg-primary ${isTyping ? "h-10 animate-wave-2" : "h-5 animate-wave-2"}`} />
        <span className={`w-1 rounded-full bg-amber-400 ${isTyping ? "h-14 animate-wave-3" : "h-8 animate-wave-3"}`} />
        <span className={`w-1 rounded-full bg-primary ${isTyping ? "h-10 animate-wave-4" : "h-5 animate-wave-4"}`} />
        <span className={`w-1 rounded-full bg-primary ${isTyping ? "h-6 animate-wave-1" : "h-3 animate-wave-1"}`} />
      </div>
    </div>
  );
}
