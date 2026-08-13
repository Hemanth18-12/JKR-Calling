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
    <div className="space-y-6 p-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold text-foreground">Calls</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Every call this workspace has run — mock or otherwise.
          </p>
        </div>
        <div className="flex items-center gap-2 rounded-xl border border-secondary/30 bg-secondary/5 px-4 py-2 text-xs text-secondary">
          <PhoneCall className="h-3.5 w-3.5" />
          Mock telephony active · calls complete instantly
        </div>
      </div>

      {/* Filter tabs */}
      <div className="flex items-center gap-1 rounded-xl border border-border bg-surface p-1">
        {[
          { key: "all", href: "/app/calls" as const, label: "All calls", count: calls.length },
          { key: "campaign", href: "/app/calls?filter=campaign" as const, label: "Campaign", count: campaignCount },
          { key: "test", href: "/app/calls?filter=test" as const, label: "Test lab", count: testCount },
        ].map((tab) => (
          <Link
            key={tab.key}
            href={tab.href}
            className={`flex items-center gap-1.5 rounded-lg px-4 py-1.5 text-sm font-medium transition-all ${
              filter === tab.key
                ? "bg-primary text-primary-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {tab.label}
            <span
              className={`rounded-full px-1.5 py-0.5 text-xs ${
                filter === tab.key ? "bg-white/20" : "bg-surface-raised text-muted-foreground"
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
        <Card>
          <CardContent className="p-0">
            <div className="divide-y divide-border">
              {filteredCalls.map((c) => (
                <Link
                  key={c.call_id}
                  href={`/app/calls/${c.call_id}`}
                  className="flex items-center justify-between px-5 py-3.5 text-sm transition-colors hover:bg-surface-raised"
                >
                  <div className="flex items-center gap-3">
                    <div
                      className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${
                        c.campaign_id
                          ? "border border-primary/20 bg-primary/10 text-primary"
                          : "border border-border bg-surface text-muted-foreground"
                      }`}
                    >
                      {c.campaign_id ? <Megaphone className="h-3.5 w-3.5" /> : <Phone className="h-3.5 w-3.5" />}
                    </div>
                    <div>
                      <p className="font-medium text-foreground">{c.contact_name ?? "Test call"}</p>
                      <p className="text-xs text-muted-foreground">
                        {c.direction} ·{" "}
                        {c.started_at
                          ? new Date(c.started_at).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" })
                          : "not started"}
                        {c.duration_seconds != null ? ` · ${c.duration_seconds}s` : ""}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {c.campaign_id ? (
                      <Badge variant="secondary" className="text-xs">
                        Campaign
                      </Badge>
                    ) : null}
                    {c.is_mock ? (
                      <Badge variant="outline" className="text-xs text-muted-foreground">
                        mock
                      </Badge>
                    ) : null}
                    {c.outcome_category ? (
                      <Badge variant="outline" className="text-xs">
                        {c.outcome_category.replace(/_/g, " ")}
                      </Badge>
                    ) : null}
                    <Badge variant={CALL_STATUS_VARIANT[c.status] ?? "secondary"}>
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
