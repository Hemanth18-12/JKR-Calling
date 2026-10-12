import { CALL_STATUS_VARIANT } from "@jkr/contracts";
import { callsApi } from "@jkr/sdk";
import { Badge, Card, CardContent, EmptyState } from "@jkr/ui";
import { Megaphone, Phone, PhoneCall } from "lucide-react";
import Link from "next/link";
import { notFound } from "next/navigation";

import { getActiveWorkspaceContext } from "@/lib/session";

export default async function CallsPage({
  searchParams,
}: {
  searchParams: Promise<{ filter?: string }>;
}) {
  const { workspace, cookieHeader } = await getActiveWorkspaceContext();
  if (!workspace) notFound();

  const params = await searchParams;
  const filter = params.filter ?? "all";

  const calls = await callsApi.list(workspace.id, undefined, { cookieHeader });

  const filteredCalls =
    filter === "campaign"
      ? calls.filter((c) => c.campaign_id)
      : filter === "test"
        ? calls.filter((c) => !c.campaign_id)
        : calls;

  const campaignCount = calls.filter((c) => c.campaign_id).length;
  const testCount = calls.filter((c) => !c.campaign_id).length;

  return (
    <div className="space-y-6 p-4 sm:p-8 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl sm:text-3xl font-bold tracking-tight text-foreground">Calls</h1>
          <p className="mt-1 text-xs sm:text-sm text-muted-foreground">
            Every call this workspace has run: live telephony, campaigns, and mock tests.
          </p>
        </div>
        <div className="flex items-center gap-2 rounded-xl border border-amber-500/30 bg-gradient-to-r from-amber-500/10 via-orange-500/10 to-amber-500/15 px-4 py-2 text-xs text-amber-500 font-medium shadow-xs shadow-amber-500/10">
          <PhoneCall className="h-3.5 w-3.5 shrink-0" />
          <span>Mock telephony active · calls complete instantly</span>
        </div>
      </div>

      {/* Filter tabs */}
      <div id="tour-calls-filter" className="flex items-center gap-1.5 rounded-xl border border-border/80 bg-surface/85 backdrop-blur-md p-1.5 shadow-xs w-fit">
        {[
          { key: "all", href: "/app/calls" as const, label: "All calls", count: calls.length },
          { key: "campaign", href: "/app/calls?filter=campaign" as const, label: "Campaign", count: campaignCount },
          { key: "test", href: "/app/calls?filter=test" as const, label: "Test lab", count: testCount },
        ].map((tab) => (
          <Link
            key={tab.key}
            href={tab.href}
            className={`flex items-center gap-2 rounded-lg px-3.5 py-1.5 text-xs sm:text-sm font-medium transition-all ${
              filter === tab.key
                ? "bg-gradient-to-r from-amber-400 via-primary to-yellow-400 text-black font-semibold shadow-sm shadow-amber-400/25"
                : "text-muted-foreground hover:bg-surface-raised hover:text-foreground"
            }`}
          >
            <span>{tab.label}</span>
            <span
              className={`rounded-full px-1.5 py-0.2 text-[11px] font-mono ${
                filter === tab.key ? "bg-black/15 text-black font-bold" : "bg-surface-raised border border-border/60 text-muted-foreground"
              }`}
            >
              {tab.count}
            </span>
          </Link>
        ))}
      </div>

      {filteredCalls.length === 0 ? (
        <EmptyState
          icon={filter === "campaign" ? Megaphone : Phone}
          title={filter === "campaign" ? "No campaign calls yet" : filter === "test" ? "No test calls yet" : "No calls yet"}
          description={
            filter === "campaign"
              ? "Launch a campaign to generate calls. Make sure the campaign's calling hours window covers the current time (IST)."
              : "Start a Test Lab call from an agent's page to see it here."
          }
        />
      ) : (
        <Card id="tour-calls-list" className="border-border/80 bg-surface/85 backdrop-blur-md shadow-subtle hover:border-primary/30 transition-all rounded-xl overflow-hidden">
          <CardContent className="p-0">
            <div className="divide-y divide-border/60">
              {filteredCalls.map((c) => (
                <Link
                  key={c.call_id}
                  href={`/app/calls/${c.call_id}`}
                  className="flex items-center justify-between px-5 py-4 text-sm transition-all hover:bg-surface-raised/80 hover:translate-x-0.5 group"
                >
                  <div className="flex items-center gap-3.5">
                    <div
                      className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl shadow-xs transition-transform group-hover:scale-105 ${
                        c.campaign_id
                          ? "border border-amber-500/30 bg-gradient-to-br from-amber-500/20 to-primary/20 text-amber-500"
                          : "border border-indigo-500/30 bg-gradient-to-br from-indigo-500/15 via-purple-500/15 to-pink-500/10 text-indigo-500 dark:text-indigo-400"
                      }`}
                    >
                      {c.campaign_id ? <Megaphone className="h-4 w-4" /> : <Phone className="h-4 w-4" />}
                    </div>
                    <div>
                      <p className="font-semibold text-foreground text-xs sm:text-sm group-hover:text-primary transition-colors">
                        {c.contact_name ?? "Test call"}
                      </p>
                      <p className="text-[11px] text-muted-foreground flex items-center gap-1.5 mt-0.5">
                        <span className="capitalize">{c.direction}</span>
                        <span>·</span>
                        <span>
                          {c.started_at
                            ? new Date(c.started_at).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" })
                            : "not started"}
                        </span>
                        {c.duration_seconds != null ? (
                          <>
                            <span>·</span>
                            <span className="font-mono tabular-nums text-foreground/80">{c.duration_seconds}s</span>
                          </>
                        ) : null}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {c.campaign_id ? (
                      <Badge variant="secondary" className="text-[11px]">
                        Campaign
                      </Badge>
                    ) : null}
                    {c.is_mock ? (
                      <span className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground bg-surface-raised px-2 py-0.5 rounded border border-border/60">
                        mock
                      </span>
                    ) : null}
                    {c.outcome_category ? (
                      <span
                        className={`text-[11px] font-medium px-2 py-0.5 rounded-full capitalize border ${
                          c.outcome_category === "qualified"
                            ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                            : c.outcome_category === "unreachable"
                            ? "border-rose-500/30 bg-rose-500/10 text-rose-600 dark:text-rose-400"
                            : "border-border bg-surface-raised text-muted-foreground"
                        }`}
                      >
                        {c.outcome_category.replace(/_/g, " ")}
                      </span>
                    ) : null}
                    <Badge variant={CALL_STATUS_VARIANT[c.status] ?? "secondary"} className="text-[11px]">
                      {c.status.replace(/_/g, " ")}
                    </Badge>
                  </div>
                </Link>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
