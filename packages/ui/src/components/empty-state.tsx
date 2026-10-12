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
        "relative flex flex-col items-center justify-center gap-4 rounded-xl border border-dashed border-border/80 bg-surface/30 p-10 text-center",
        className
      )}
    >
      {Icon ? (
        <div className="flex h-12 w-12 items-center justify-center rounded-xl border border-border/80 bg-surface-raised text-foreground/80">
          <Icon className="h-5 w-5" />
        </div>
      ) : null}

      <div className="space-y-1">
        <p className="font-display text-base font-semibold text-foreground">{title}</p>
        {description ? <p className="max-w-sm text-xs sm:text-sm text-muted-foreground">{description}</p> : null}
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
