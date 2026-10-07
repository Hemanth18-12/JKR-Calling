import { billingApi, coinsApi } from "@jkr/sdk";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, EmptyState } from "@jkr/ui";
import { Building2, Coins, PhoneCall, Tag, Users, Zap } from "lucide-react";
import Link from "next/link";

import { UsageSummaryView } from "@/components/usage-summary";
import { getActiveWorkspaceContext } from "@/lib/session";

export default async function UsagePage() {
  const { workspace, cookieHeader } = await getActiveWorkspaceContext();
  if (!workspace) {
    return (
      <div className="p-8">
        <EmptyState icon={Building2} title="No workspace yet" description="Select or create a workspace to view usage." />
      </div>
    );
  }

  const [usageResult, walletResult] = await Promise.allSettled([
    billingApi.usage(workspace.id, { cookieHeader }),
    coinsApi.getWallet(workspace.id, { cookieHeader }),
  ]);

  const usage =
    usageResult.status === "fulfilled"
      ? usageResult.value
      : {
          usage_by_type: [],
          total_calls: 0,
          total_call_seconds: 0,
          campaign_budgets: [],
        };

  const wallet = walletResult.status === "fulfilled" ? walletResult.value : null;
  const balanceCoins = wallet?.balance_coins ?? 0;
  const balanceMinutes = Math.floor(balanceCoins / 60);

  return (
    <div className="space-y-6 p-6 sm:p-8 max-w-7xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground sm:text-3xl">Usage &amp; Telemetry</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Real metered telemetry from actual voice calls — exact per-second billing with zero rounding padding.
        </p>
      </div>

      {/* OmniDimension-Style Summary Strip */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border/80 bg-surface px-4 py-3 shadow-sm sm:px-6">
        <div className="flex flex-wrap items-center gap-3 text-xs sm:text-sm text-foreground">
          <div className="flex items-center gap-1.5 font-bold">
            <Building2 className="h-4 w-4 text-primary" />
            <span>{workspace.name}</span>
          </div>

          <span className="text-border">•</span>

          <div className="flex items-center gap-1.5">
            <Coins className="h-4 w-4 text-primary" />
            <span>
              Balance: 🪙 <strong>{balanceCoins.toLocaleString()}</strong>{" "}
              <span className="text-muted-foreground">({balanceMinutes}m talk time)</span>
            </span>
          </div>

          <span className="text-border">•</span>

          <div className="flex items-center gap-1.5">
            <Tag className="h-4 w-4 text-emerald-400" />
            <span>
              Rate: <strong className="text-foreground">1 coin / sec</strong>
            </span>
          </div>

          <span className="text-border">•</span>

          <div className="flex items-center gap-1.5">
            <Zap className="h-4 w-4 text-amber-400" />
            <span>
              Concurrency: <strong className="text-foreground">5 simultaneous channels</strong>
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Link
            href="/app/team"
            className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-surface-raised px-3 py-1.5 text-xs font-semibold text-foreground hover:border-primary transition"
          >
            <Users className="h-3.5 w-3.5" />
            <span>Team &amp; Limits</span>
          </Link>
          <Link
            href="/app/billing"
            className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-xs font-bold text-black hover:bg-primary/90 transition shadow-sm"
          >
            <Coins className="h-3.5 w-3.5" />
            <span>Add Coins</span>
          </Link>
        </div>
      </div>

      {/* Telemetry Meter View */}
      <UsageSummaryView usage={usage} />
    </div>
  );
}
