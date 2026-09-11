import { type VariantProps, cva } from "class-variance-authority";
import * as React from "react";

import { cn } from "../utils";

export const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium transition-all duration-150",
  {
    variants: {
      variant: {
        default: "border-primary/40 bg-primary/15 text-primary font-medium",
        secondary: "border-border bg-surface-raised text-muted-foreground",
        success: "border-emerald-500/30 bg-emerald-500/15 text-emerald-400 font-medium",
        warning: "border-amber-500/40 bg-amber-500/15 text-amber-400",
        danger: "border-danger/40 bg-danger/15 text-danger font-medium",
        outline: "border-border/70 text-muted-foreground",
        live: "border-secondary/50 bg-secondary/15 text-secondary font-medium shadow-[0_0_8px_rgba(255,159,28,0.35)]",
        mock: "border-dashed border-zinc-700 bg-zinc-900/60 text-zinc-400 font-medium",
      },
    },
    defaultVariants: { variant: "default" },
  }
);

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}
