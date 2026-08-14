"use client";

import { Button } from "@jkr/ui";
import { ArrowLeft } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";

interface BackButtonProps {
  fallbackHref?: string;
  label?: string;
  className?: string;
  variant?: "ghost" | "outline" | "default" | "secondary";
  size?: "default" | "sm" | "lg" | "icon";
  showLabel?: boolean;
}

export function BackButton({
  fallbackHref = "/app/dashboard",
  label = "Back",
  className = "",
  variant = "ghost",
  size = "sm",
  showLabel = true,
}: BackButtonProps) {
  const router = useRouter();

  const handleBack = () => {
    if (typeof window !== "undefined" && window.history.length > 1) {
      router.back();
    } else {
      router.push(fallbackHref as never);
    }
  };

  return (
    <Button
      type="button"
      variant={variant}
      size={size}
      onClick={handleBack}
      className={`group flex items-center gap-1.5 text-muted-foreground hover:text-foreground transition-all duration-150 ${className}`}
      title={label}
      aria-label={label}
    >
      <ArrowLeft className="h-4 w-4 transition-transform duration-150 group-hover:-translate-x-0.5" />
      {showLabel ? <span className="text-xs font-medium">{label}</span> : null}
    </Button>
  );
}
