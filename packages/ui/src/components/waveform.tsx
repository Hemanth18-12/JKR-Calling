"use client";

import * as React from "react";
import { cn } from "../utils";

export interface VoiceWaveformProps extends React.HTMLAttributes<HTMLDivElement> {
  active?: boolean;
  bars?: number;
  size?: "sm" | "md" | "lg";
  variant?: "live" | "brand" | "amber";
}

export function VoiceWaveform({
  active = true,
  bars = 5,
  size = "md",
  variant = "live",
  className,
  ...props
}: VoiceWaveformProps) {
  const barColor =
    variant === "live"
      ? "bg-secondary"
      : variant === "brand"
        ? "bg-primary"
        : "bg-amber-500";

  const sizeStyles = {
    sm: { container: "h-4 gap-[2px]", bar: "w-[2px]" },
    md: { container: "h-6 gap-[3px]", bar: "w-[3px]" },
    lg: { container: "h-10 gap-1", bar: "w-1" },
  }[size];

  const animations = [
    "animate-wave-1",
    "animate-wave-2",
    "animate-wave-3",
    "animate-wave-4",
    "animate-wave-1",
  ];

  return (
    <div
      aria-label={active ? "Live audio active" : "Audio idle"}
      className={cn("flex items-center justify-center", sizeStyles.container, className)}
      {...props}
    >
      {Array.from({ length: bars }).map((_, i) => (
        <span
          key={i}
          className={cn(
            "rounded-full transition-all duration-300",
            barColor,
            sizeStyles.bar,
            active ? animations[i % animations.length] : "h-1 opacity-40"
          )}
        />
      ))}
    </div>
  );
}

export interface CallPulseProps extends React.HTMLAttributes<HTMLDivElement> {
  active?: boolean;
  isMock?: boolean;
  size?: "sm" | "md" | "lg";
}

export function CallPulse({
  active = true,
  isMock = false,
  size = "md",
  className,
  ...props
}: CallPulseProps) {
  const sizeClasses = {
    sm: "h-2 w-2",
    md: "h-3 w-3",
    lg: "h-4 w-4",
  }[size];

  if (isMock) {
    return (
      <span className={cn("relative flex items-center justify-center", className)} title="Mock telephony provider" {...props}>
        <span className={cn("rounded-full border border-dashed border-zinc-600 bg-zinc-800/80", sizeClasses)} />
      </span>
    );
  }

  return (
    <span className={cn("relative flex items-center justify-center", className)} title="Live audio stream active" {...props}>
      {active && (
        <span
          className={cn(
            "absolute inline-flex rounded-full bg-amber-500/40 animate-ping duration-1000",
            size === "sm" ? "h-2.5 w-2.5" : size === "md" ? "h-3.5 w-3.5" : "h-5 w-5"
          )}
        />
      )}
      <span className={cn("relative inline-flex rounded-full bg-amber-500", sizeClasses)} />
    </span>
  );
}
