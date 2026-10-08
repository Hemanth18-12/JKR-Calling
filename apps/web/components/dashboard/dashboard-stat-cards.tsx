"use client";

import * as React from "react";
import { motion, useSpring, useTransform } from "framer-motion";
import { Card, CardContent } from "@jkr/ui";

interface StatItem {
  key: string;
  label: string;
  rawValue: number;
  formattedValue?: string;
  icon: string;
  accent: "primary" | "amber" | "danger";
  isPct?: boolean;
  isRevenue?: boolean;
  stagger: number;
}

function AnimatedNumber({ value }: { value: number }) {
  const spring = useSpring(0, { mass: 0.8, stiffness: 75, damping: 15 });
  const display = useTransform(spring, (current) => Math.round(current).toLocaleString("en-IN"));

  React.useEffect(() => {
    spring.set(value);
  }, [spring, value]);

  return <motion.span>{display}</motion.span>;
}

function InteractiveStatCard({ item }: { item: StatItem }) {
  const cardRef = React.useRef<HTMLDivElement>(null);
  const [mousePos, setMousePos] = React.useState({ x: 50, y: 50, active: false });

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!cardRef.current) return;
    const rect = cardRef.current.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * 100;
    const y = ((e.clientY - rect.top) / rect.height) * 100;
    setMousePos({ x, y, active: true });
  };

  const handleMouseLeave = () => {
    setMousePos((prev) => ({ ...prev, active: false }));
  };

  const accentClasses = {
    primary: "text-primary border-primary/30 bg-primary/10 shadow-sm shadow-primary/10",
    amber: "text-amber-400 border-amber-500/30 bg-amber-500/10 shadow-sm shadow-amber-500/10",
    danger: "text-danger border-danger/30 bg-danger/10 shadow-sm shadow-danger/10",
  }[item.accent];

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay: item.stagger * 0.05, ease: [0.16, 1, 0.3, 1] }}
      whileHover={{ y: -4, transition: { duration: 0.2 } }}
      className="perspective-1000"
    >
      <Card
        ref={cardRef}
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
        className="relative overflow-hidden border-border/80 bg-surface/90 shadow-card-raised transition-all duration-300 hover:border-primary/40 hover:shadow-2xl"
      >
        {/* Specular Spotlight Glare following cursor */}
        <div
          className="pointer-events-none absolute inset-0 z-10 transition-opacity duration-300"
          style={{
            opacity: mousePos.active ? 0.35 : 0,
            background: `radial-gradient(circle at ${mousePos.x}% ${mousePos.y}%, rgba(255, 212, 0, 0.22) 0%, transparent 65%)`,
          }}
          aria-hidden="true"
        />

        <CardContent className="p-5 relative z-20">
          <div className="mb-3 flex items-center justify-between">
            <span className={`flex h-8 w-8 items-center justify-center rounded-lg border text-sm ${accentClasses}`}>
              {item.icon}
            </span>
          </div>
          <p className="font-display text-2xl font-bold tabular-nums text-foreground flex items-center gap-1">
            {item.isRevenue && <span className="text-amber-400">₹</span>}
            {item.isPct ? (
              <span>{Math.round(item.rawValue * 100)}%</span>
            ) : (
              <AnimatedNumber value={item.rawValue} />
            )}
          </p>
          <p className="mt-0.5 text-xs text-muted-foreground">{item.label}</p>
        </CardContent>
      </Card>
    </motion.div>
  );
}

export function DashboardStatCards({ items }: { items: StatItem[] }) {
  return (
    <div id="tour-kpi-cards" className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {items.map((item) => (
        <InteractiveStatCard key={item.key} item={item} />
      ))}
    </div>
  );
}
