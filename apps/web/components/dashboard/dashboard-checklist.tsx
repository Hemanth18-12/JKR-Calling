"use client";

import { CheckCircle2, Circle, ArrowRight, Bot, FileText, PhoneCall, Megaphone } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { Button, Card, CardContent } from "@jkr/ui";

interface SetupChecklistProps {
  hasAgents: boolean;
  hasKnowledge: boolean;
  hasCalls: boolean;
  hasCampaigns: boolean;
}

export function SetupChecklist({
  hasAgents,
  hasKnowledge,
  hasCalls,
  hasCampaigns,
}: SetupChecklistProps) {
  const steps = [
    {
      id: "agent",
      title: "Create an agent",
      description: "Pick an Indian voice persona and greeting",
      completed: hasAgents,
      href: "/app/agents/new",
      actionText: "Create agent",
      icon: Bot,
    },
    {
      id: "knowledge",
      title: "Add knowledge",
      description: "Upload clinic, school, or business FAQs",
      completed: hasKnowledge,
      href: "/app/knowledge/documents",
      actionText: "Add FAQ",
      icon: FileText,
    },
    {
      id: "test",
      title: "Run a test call",
      description: "Speak with your agent in Test Lab",
      completed: hasCalls,
      href: "/app/agents",
      actionText: "Test call",
      icon: PhoneCall,
    },
    {
      id: "campaign",
      title: "Launch a campaign",
      description: "Upload contacts and schedule calling hours",
      completed: hasCampaigns,
      href: "/app/campaigns/new",
      actionText: "New campaign",
      icon: Megaphone,
    },
  ];

  const completedCount = steps.filter((s) => s.completed).length;
  const isFullySetup = completedCount === steps.length;

  if (isFullySetup) {
    return null; // Automatically hidden once workspace is fully set up
  }

  const progressPercent = Math.round((completedCount / steps.length) * 100);

  return (
    <Card className="border-border/80 bg-surface">
      <CardContent className="p-5">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="font-display text-sm font-semibold text-foreground">
                Workspace Setup Checklist
              </span>
              <span className="text-[11px] font-mono px-2 py-0.5 rounded-full bg-primary/10 text-primary font-bold">
                {completedCount} of {steps.length} complete
              </span>
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">
              Complete these 4 steps to launch automated multilingual calling.
            </p>
          </div>

          <div className="w-full sm:w-44">
            <div className="flex justify-between text-[11px] text-muted-foreground mb-1">
              <span>Progress</span>
              <span className="font-mono font-semibold tabular-nums text-foreground">{progressPercent}%</span>
            </div>
            <div className="h-1.5 w-full bg-surface-raised rounded-full overflow-hidden border border-border/60">
              <div
                className="h-full bg-primary rounded-full transition-all duration-300"
                style={{ width: `${progressPercent}%` }}
              />
            </div>
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {steps.map((step) => {
            const Icon = step.icon;
            return (
              <div
                key={step.id}
                className={`flex flex-col justify-between p-3.5 rounded-xl border transition-colors ${
                  step.completed
                    ? "bg-surface-raised/40 border-border/60"
                    : "bg-surface-raised/80 border-border hover:border-primary/40"
                }`}
              >
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <Icon className="h-4 w-4 text-muted-foreground" />
                      <span className="text-xs font-semibold text-foreground">{step.title}</span>
                    </div>
                    {step.completed ? (
                      <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
                    ) : (
                      <Circle className="h-4 w-4 text-muted-foreground/40 shrink-0" />
                    )}
                  </div>
                  <p className="text-[11px] text-muted-foreground leading-snug">{step.description}</p>
                </div>

                {!step.completed ? (
                  <div className="mt-3 pt-2 border-t border-border/60">
                    <Link
                      href={step.href as never}
                      className="inline-flex items-center gap-1 text-[11px] font-semibold text-primary hover:underline"
                    >
                      <span>{step.actionText}</span>
                      <ArrowRight className="h-3 w-3" />
                    </Link>
                  </div>
                ) : (
                  <div className="mt-3 pt-2 border-t border-border/40 text-[11px] text-muted-foreground/70 font-medium">
                    Completed
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
