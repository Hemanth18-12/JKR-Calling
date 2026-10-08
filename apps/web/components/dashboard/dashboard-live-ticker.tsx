"use client";

import * as React from "react";
import { Radio, Bot, UploadCloud } from "lucide-react";
import Link from "next/link";
import { Card, CardContent } from "@jkr/ui";

export function DashboardLiveTicker() {
  return (
    <div id="tour-quick-actions" className="grid gap-4 md:grid-cols-3">
      {/* Active Telephony Channel status with animated audio visualizer */}
      <Card className="border-secondary/40 bg-secondary/10 shadow-sm relative overflow-hidden group">
        <div className="absolute -right-6 -bottom-6 w-24 h-24 bg-secondary/15 rounded-full blur-xl pointer-events-none" />
        <CardContent className="flex items-center justify-between p-4 relative z-10">
          <div className="flex items-center gap-3">
            <div className="relative flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-secondary/20 text-secondary border border-secondary/30">
              <Radio className="h-4 w-4 animate-pulse" />
              <span className="absolute -top-1 -right-1 flex h-2.5 w-2.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-secondary opacity-75" />
                <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-secondary" />
              </span>
            </div>
            <div className="text-xs">
              <p className="font-semibold text-foreground flex items-center gap-1.5">
                Live Telephony Pipeline
                <span className="text-[10px] text-secondary font-mono px-1.5 py-0.2 bg-secondary/20 rounded font-bold">READY</span>
              </p>
              <p className="text-muted-foreground mt-0.5">Dograh Engine · SIP Dialer Connected</p>
            </div>
          </div>

          {/* Mini Live Audio Frequency Bars */}
          <div className="flex items-end gap-0.5 h-6 px-2 py-1 bg-black/40 rounded-md border border-secondary/20" title="Audio engine ready">
            <span className="w-1 bg-secondary rounded-full animate-[pulse_1s_ease-in-out_infinite] h-2" />
            <span className="w-1 bg-secondary rounded-full animate-[pulse_1.2s_ease-in-out_infinite_0.2s] h-4" />
            <span className="w-1 bg-secondary rounded-full animate-[pulse_0.9s_ease-in-out_infinite_0.4s] h-5" />
            <span className="w-1 bg-secondary rounded-full animate-[pulse_1.4s_ease-in-out_infinite_0.1s] h-3" />
            <span className="w-1 bg-secondary rounded-full animate-[pulse_1.1s_ease-in-out_infinite_0.3s] h-2" />
          </div>
        </CardContent>
      </Card>

      {/* Quick Action: Test Agent Call */}
      <Link href="/app/agents">
        <Card className="hover:border-primary/50 transition-all duration-300 hover:shadow-lg hover:-translate-y-0.5 cursor-pointer h-full border-border/80 bg-surface/90">
          <CardContent className="flex items-center gap-3 p-4">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/15 text-primary border border-primary/20 transition-transform group-hover:scale-110">
              <Bot className="h-5 w-5" />
            </div>
            <div className="text-xs">
              <p className="font-semibold text-foreground">Test AI Voice Agent</p>
              <p className="text-muted-foreground mt-0.5">Open Test Lab in browser or SIP dialer →</p>
            </div>
          </CardContent>
        </Card>
      </Link>

      {/* Quick Action: Upload Contacts */}
      <Link href="/app/contacts">
        <Card className="hover:border-amber-500/50 transition-all duration-300 hover:shadow-lg hover:-translate-y-0.5 cursor-pointer h-full border-border/80 bg-surface/90">
          <CardContent className="flex items-center gap-3 p-4">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-amber-500/15 text-amber-500 border border-amber-500/20">
              <UploadCloud className="h-5 w-5" />
            </div>
            <div className="text-xs">
              <p className="font-semibold text-foreground">Import Contact Lists</p>
              <p className="text-muted-foreground mt-0.5">CSV bulk upload with consent logging →</p>
            </div>
          </CardContent>
        </Card>
      </Link>
    </div>
  );
}
