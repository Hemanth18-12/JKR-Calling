"use client";

import React from "react";
import { Button } from "@jkr/ui";
import { Sparkles, Headphones } from "lucide-react";
import { useGuidedTour } from "./guided-tour-context";

interface StartTourButtonProps {
  pageId?: string;
  variant?: "default" | "outline" | "gradient" | "ghost";
  size?: "default" | "sm" | "lg" | "icon";
  className?: string;
  label?: string;
}

export function StartTourButton({
  pageId = "dashboard",
  variant = "gradient",
  size = "sm",
  className = "",
  label = "Start guided tour",
}: StartTourButtonProps) {
  const { startTour, isOpen } = useGuidedTour();

  return (
    <Button
      variant={variant}
      size={size}
      onClick={() => startTour(pageId)}
      className={`relative group gap-1.5 shadow-md shadow-primary/20 hover:shadow-primary/40 transition-all duration-200 ${className}`}
      title="Listen to an AI voice walkthrough of this page"
    >
      <Headphones className="h-3.5 w-3.5 text-white transition-transform group-hover:scale-110" />
      <span>{label}</span>
      <Sparkles className="h-3 w-3 text-amber-300 animate-pulse" />
    </Button>
  );
}
