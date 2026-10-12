import { type VariantProps, cva } from "class-variance-authority";
import * as React from "react";

import { cn } from "../utils";

export const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium transition-colors",
  {
    variants: {
      variant: {
        default: "border-primary/30 bg-primary/10 text-primary font-medium",
        secondary: "border-border/80 bg-surface-raised text-muted-foreground",
        success: "border-emerald-500/30 bg-emerald-500/10 text-emerald-400 font-medium",
        warning: "border-amber-500/30 bg-amber-500/10 text-amber-400 font-medium",
        danger: "border-rose-500/30 bg-rose-500/10 text-rose-400 font-medium",
        outline: "border-border/70 text-muted-foreground",
        live: "border-amber-500/40 bg-amber-500/10 text-amber-400 font-medium",
        mock: "border border-dashed border-border/80 bg-surface-raised/40 text-muted-foreground font-mono text-[11px]",
      },
    },
    defaultVariants: { variant: "default" },
  }
);

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}
