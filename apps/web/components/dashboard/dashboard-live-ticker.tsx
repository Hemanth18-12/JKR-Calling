"use client";

import * as React from "react";
import { Radio, Bot, UploadCloud, ArrowRight } from "lucide-react";
import Link from "next/link";
import { Card, CardContent } from "@jkr/ui";

export function DashboardLiveTicker() {
  return (
    <div id="tour-quick-actions" className="grid gap-3 sm:grid-cols-3">
      {/* Active Telephony Channel status */}
      <Card className="border-border/80 bg-surface shadow-subtle">
        <CardContent className="flex items-center justify-between p-4">
          <div className="flex items-center gap-3">
            <div className="relative flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-surface-raised border border-border text-foreground">
              <Radio className="h-4 w-4 text-amber-400" />
              <span className="absolute -top-0.5 -right-0.5 flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-amber-400" />
              </span>
            </div>
            <div className="text-xs">
              <p className="font-semibold text-foreground flex items-center gap-1.5">
                Telephony Pipeline
                <span className="text-[10px] text-amber-400 font-mono px-1 py-0.2 bg-amber-500/10 border border-amber-500/20 rounded font-bold">
                  Active
                </span>
              </p>
              <p className="text-muted-foreground mt-0.5">Dograh Engine / SIP Dialer</p>
            </div>
          </div>

          {/* Mini Live Audio Frequency Bars */}
          <div className="flex items-end gap-[2px] h-5 px-2 py-1 bg-surface-raised rounded border border-border/80" title="Audio pipeline ready">
            <span className="w-[2px] bg-amber-400 rounded-full animate-wave-1 h-2" />
            <span className="w-[2px] bg-amber-400 rounded-full animate-wave-2 h-4" />
            <span className="w-[2px] bg-amber-400 rounded-full animate-wave-3 h-5" />
            <span className="w-[2px] bg-amber-400 rounded-full animate-wave-4 h-3" />
          </div>
        </CardContent>
      </Card>

      {/* Quick Action: Test Agent Call */}
      <Link href="/app/agents">
        <Card className="border-border/80 bg-surface hover:border-primary/40 hover:bg-surface-raised/40 transition-colors cursor-pointer h-full shadow-subtle">
          <CardContent className="flex items-center justify-between p-4">
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary border border-primary/20">
                <Bot className="h-4 w-4" />
              </div>
              <div className="text-xs">
                <p className="font-semibold text-foreground">Test AI Agent</p>
                <p className="text-muted-foreground mt-0.5">Launch interactive Test Lab</p>
              </div>
            </div>
            <ArrowRight className="h-4 w-4 text-muted-foreground" />
          </CardContent>
        </Card>
      </Link>

      {/* Quick Action: Upload Contacts */}
      <Link href="/app/contacts">
        <Card className="border-border/80 bg-surface hover:border-primary/40 hover:bg-surface-raised/40 transition-colors cursor-pointer h-full shadow-subtle">
          <CardContent className="flex items-center justify-between p-4">
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-surface-raised text-foreground border border-border">
                <UploadCloud className="h-4 w-4" />
              </div>
              <div className="text-xs">
                <p className="font-semibold text-foreground">Import Contacts</p>
                <p className="text-muted-foreground mt-0.5">CSV upload with consent check</p>
              </div>
            </div>
            <ArrowRight className="h-4 w-4 text-muted-foreground" />
          </CardContent>
        </Card>
      </Link>
    </div>
  );
}
