import { type VariantProps, cva } from "class-variance-authority";
import { Loader2 } from "lucide-react";
import * as React from "react";

import { cn } from "../utils";

export const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-lg text-sm font-medium transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:pointer-events-none disabled:opacity-40 active:scale-95",
  {
    variants: {
      variant: {
        default:
          "bg-primary text-primary-foreground font-semibold shadow-md shadow-primary/25 hover:bg-[#FFE033] hover:shadow-primary/45 hover:shadow-lg hover:-translate-y-[1px] active:translate-y-0",
        gradient:
          "bg-gradient-to-r from-[#FFD400] to-[#FFA000] text-black font-semibold shadow-md shadow-primary/25 hover:brightness-105 hover:shadow-primary/45 hover:shadow-lg hover:-translate-y-[1px] active:translate-y-0",
        secondary:
          "bg-surface-raised text-foreground border border-border hover:border-primary/50 hover:bg-surface-raised/80 hover:text-primary hover:-translate-y-[1px]",
        outline:
          "border border-border bg-transparent hover:bg-surface-raised hover:border-primary/50 hover:text-primary text-foreground hover:-translate-y-[1px]",
        ghost:
          "hover:bg-surface-raised hover:text-foreground text-muted-foreground",
        destructive:
          "bg-danger/15 text-danger border border-danger/30 hover:bg-danger/25 hover:border-danger/60",
        link:
          "text-primary underline-offset-4 hover:underline p-0 h-auto font-medium",
        live:
          "bg-secondary/15 text-secondary border border-secondary/40 hover:bg-secondary/25 hover:border-secondary/70 shadow-sm shadow-secondary/20 font-medium",
      },
      size: {
        default: "h-10 px-4 py-2",
        sm: "h-8 rounded-md px-3 text-xs",
        lg: "h-12 rounded-xl px-8 text-base",
        icon: "h-10 w-10",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  loading?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, loading, children, disabled, ...props }, ref) => (
    <button
      ref={ref}
      className={cn(buttonVariants({ variant, size }), className)}
      disabled={disabled || loading}
      {...props}
    >
      {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
      {children}
    </button>
  )
);
Button.displayName = "Button";
