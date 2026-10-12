"use client";

import * as React from "react";
import { motion, useSpring, useTransform } from "framer-motion";
import { Card, CardContent } from "@jkr/ui";
import {
  Calendar,
  PhoneIncoming,
  CheckCircle2,
  Coins,
  type LucideIcon,
} from "lucide-react";

const ICON_MAP: Record<string, LucideIcon> = {
  calendar: Calendar,
  appointments_booked: Calendar,
  phone: PhoneIncoming,
  connect_rate: PhoneIncoming,
  check: CheckCircle2,
  revenue_event_count: CheckCircle2,
  coins: Coins,
  revenue_paise: Coins,
};

export interface StatItem {
  key: string;
  label: string;
  rawValue: number;
  formattedValue?: string;
  icon?: LucideIcon;
  iconName?: "calendar" | "phone" | "check" | "coins" | string;
  accent: "primary" | "amber" | "emerald" | "danger";
  isPct?: boolean;
  isRevenue?: boolean;
  badge?: string;
  subtext?: string;
}

function AnimatedNumber({ value }: { value: number }) {
  const spring = useSpring(0, { mass: 0.8, stiffness: 75, damping: 15 });
  const display = useTransform(spring, (current) => Math.round(current).toLocaleString("en-IN"));

  React.useEffect(() => {
    spring.set(value);
  }, [spring, value]);

  return <motion.span className="tabular-nums font-mono">{display}</motion.span>;
}

export function DashboardStatCards({ items }: { items: StatItem[] }) {
  return (
    <div id="tour-kpi-cards" className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      {items.map((item, idx) => {
        const Icon = item.icon || (item.iconName ? ICON_MAP[item.iconName] : null) || ICON_MAP[item.key] || Calendar;
        const accentColors = {
          primary: "text-primary border-primary/30 bg-primary/10",
          amber: "text-amber-400 border-amber-500/30 bg-amber-500/10",
          emerald: "text-emerald-400 border-emerald-500/30 bg-emerald-500/10",
          danger: "text-rose-400 border-rose-500/30 bg-rose-500/10",
        }[item.accent];

        return (
          <motion.div
            key={item.key}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25, delay: idx * 0.04, ease: "easeOut" }}
          >
            <Card className="border-border/80 bg-surface shadow-subtle hover:border-white/20 transition-colors">
              <CardContent className="p-4 sm:p-5">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-xs font-medium text-muted-foreground">{item.label}</span>
                  <div className={`flex h-8 w-8 items-center justify-center rounded-lg border ${accentColors}`}>
                    <Icon className="h-4 w-4" />
                  </div>
                </div>

                <div className="flex items-baseline justify-between gap-2">
                  <p className="font-display text-2xl font-bold text-foreground flex items-baseline gap-0.5">
                    {item.isRevenue && <span className="text-base text-amber-400 font-sans mr-0.5">₹</span>}
                    {item.isPct ? (
                      <span className="font-mono tabular-nums">{Math.round(item.rawValue * 100)}%</span>
                    ) : (
                      <AnimatedNumber value={item.rawValue} />
                    )}
                  </p>
                  {item.badge && (
                    <span className="text-[10px] font-semibold text-muted-foreground font-mono bg-surface-raised px-1.5 py-0.5 rounded border border-border/60">
                      {item.badge}
                    </span>
                  )}
                </div>

                {item.subtext && (
                  <p className="mt-1 text-[11px] text-muted-foreground">{item.subtext}</p>
                )}
              </CardContent>
            </Card>
          </motion.div>
        );
      })}
    </div>
  );
}
