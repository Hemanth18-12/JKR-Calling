import type { LucideIcon } from "lucide-react";
import * as React from "react";

import { cn } from "../utils";

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
}: {
  icon?: LucideIcon;
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "relative flex flex-col items-center justify-center gap-4 overflow-hidden rounded-xl border border-dashed border-border/60 p-12 text-center",
        className
      )}
    >
      {/* Ambient glow background */}
      <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
        <div className="h-40 w-40 rounded-full bg-primary/5 blur-3xl" />
      </div>

      {Icon ? (
        <div className="relative flex h-14 w-14 items-center justify-center rounded-2xl border border-primary/20 bg-primary/10">
          <Icon className="h-6 w-6 text-primary" />
        </div>
      ) : null}

      <div className="space-y-1.5">
        <p className="font-display text-base font-semibold text-foreground">{title}</p>
        {description ? <p className="max-w-xs text-sm text-muted-foreground">{description}</p> : null}
      </div>
      {action}
    </div>
  );
}

export function ErrorState({
  title = "Something went wrong",
  description,
  action,
}: {
  title?: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-danger/30 bg-danger/5 p-10 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-danger/10">
        <span className="text-lg text-danger">!</span>
      </div>
      <div className="space-y-1">
        <p className="text-sm font-semibold text-danger">{title}</p>
        {description ? <p className="text-sm text-muted-foreground">{description}</p> : null}
      </div>
      {action}
    </div>
  );
}
