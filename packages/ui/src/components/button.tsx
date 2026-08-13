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
          "bg-primary text-primary-foreground shadow-md shadow-primary/30 hover:bg-primary/90 hover:shadow-primary/50 hover:shadow-lg hover:-translate-y-[1px]",
        gradient:
          "bg-gradient-to-r from-[#7C5CFF] to-[#5B3FE4] text-white shadow-md shadow-primary/30 hover:opacity-95 hover:shadow-primary/50 hover:shadow-lg hover:-translate-y-[1px]",
        secondary:
          "bg-surface-raised text-foreground border border-border hover:border-primary/40 hover:bg-surface-raised/70 hover:-translate-y-[1px]",
        outline:
          "border border-border bg-transparent hover:bg-surface-raised hover:border-primary/40 text-foreground hover:-translate-y-[1px]",
        ghost:
          "hover:bg-surface-raised text-foreground",
        destructive:
          "bg-danger/10 text-danger border border-danger/30 hover:bg-danger/20 hover:border-danger/60",
        link:
          "text-primary underline-offset-4 hover:underline p-0 h-auto",
        live:
          "bg-secondary/10 text-secondary border border-secondary/30 hover:bg-secondary/20 hover:border-secondary/60 shadow-sm shadow-secondary/20",
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
