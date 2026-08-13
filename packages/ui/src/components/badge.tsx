import { type VariantProps, cva } from "class-variance-authority";
import * as React from "react";

import { cn } from "../utils";

export const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium transition-all duration-150",
  {
    variants: {
      variant: {
        default: "border-primary/30 bg-primary/10 text-primary",
        secondary: "border-border bg-surface-raised text-muted-foreground",
        success: "border-transparent bg-success/15 text-success",
        warning: "border-amber-500/30 bg-amber-500/10 text-amber-400",
        danger: "border-danger/30 bg-danger/10 text-danger",
        outline: "border-border/60 text-muted-foreground",
        live: "border-secondary/40 bg-secondary/10 text-secondary shadow-[0_0_6px_rgba(45,212,191,0.3)]",
        mock: "border-dashed border-amber-500/40 bg-amber-500/5 text-amber-500",
      },
    },
    defaultVariants: { variant: "default" },
  }
);

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}
