import type { BusinessOverview, CallAnalytics, ConversationQuality, ProviderAnalytics } from "@jkr/contracts";
import { Badge, Card, CardContent, CardDescription, CardHeader, CardTitle } from "@jkr/ui";

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardDescription>{label}</CardDescription>
      </CardHeader>
      <CardContent>
        <p className="text-2xl font-semibold tabular-nums">{value}</p>
      </CardContent>
    </Card>
  );
}

function Bar({ label, count, max }: { label: string; count: number; max: number }) {
  const pct = max > 0 ? Math.round((count / max) * 100) : 0;
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-xs">
        <span className="capitalize text-muted-foreground">{label.replace(/_/g, " ")}</span>
        <span className="tabular-nums">{count}</span>
      </div>
      <div className="h-2 rounded-full bg-surface-raised">
        <div className="h-2 rounded-full bg-primary" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function formatPct(value: number | null): string {
  return value === null ? "—" : `${Math.round(value * 100)}%`;
}

export function AnalyticsDashboard({
  overview, calls, quality, providers,
}: {
  overview: BusinessOverview; calls: CallAnalytics; quality: ConversationQuality; providers: ProviderAnalytics;
}) {
  const maxFunnel = Math.max(1, ...calls.funnel.map((f) => f.count));
  const maxOutcome = Math.max(1, ...calls.outcome_breakdown.map((o) => o.count));

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Total calls" value={overview.total_calls} />
        <Stat label="Connect rate" value={formatPct(overview.connect_rate)} />
        <Stat label="Appointments booked" value={overview.appointments_booked} />
        <Stat label="Contacts reached" value={overview.contacts_reached} />
        <Stat label="Active campaigns" value={overview.active_campaigns} />
        <Stat label="Pending handoffs" value={overview.pending_handoffs} />
        <Stat label="Avg call duration" value={calls.avg_duration_seconds !== null ? `${calls.avg_duration_seconds}s` : "—"} />
        <Stat label="Revenue (₹)" value={(overview.revenue_paise / 100).toLocaleString("en-IN")} />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Funnel</CardTitle>
            <CardDescription>Dialed → connected → qualified → appointment booked</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {calls.funnel.map((f) => (
              <Bar key={f.stage} label={f.stage} count={f.count} max={maxFunnel} />
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Outcomes</CardTitle>
            <CardDescription>{calls.mock_call_count} mock · {calls.real_call_count} real</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {calls.outcome_breakdown.length === 0 ? (
              <p className="text-sm text-muted-foreground">No completed calls yet.</p>
            ) : (
              calls.outcome_breakdown.map((o) => <Bar key={o.key} label={o.key} count={o.count} max={maxOutcome} />)
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Conversation quality</CardTitle>
            <CardDescription>{quality.calls_evaluated} call{quality.calls_evaluated === 1 ? "" : "s"} evaluated</CardDescription>
          </CardHeader>
          <CardContent className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <p className="text-muted-foreground">Avg overall score</p>
              <p className="text-lg font-semibold">{quality.avg_overall_score ?? "—"}</p>
            </div>
            <div>
              <p className="text-muted-foreground">Disclosure present</p>
              <p className="text-lg font-semibold">{formatPct(quality.disclosure_present_rate)}</p>
            </div>
            <div>
              <p className="text-muted-foreground">Interruption quality</p>
              <p className="text-lg font-semibold">{quality.avg_interruption_quality_score ?? "—"}</p>
            </div>
            <div>
              <p className="text-muted-foreground">Needs human review</p>
              <p className="text-lg font-semibold">{formatPct(quality.needs_human_review_rate)}</p>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Providers</CardTitle>
            <CardDescription>Latency by pipeline stage, account health</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              {providers.latency_by_stage.map((s) => (
                <div key={s.stage} className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">{s.stage.replace(/_/g, " ")}</span>
                  <span className="tabular-nums">{s.avg_duration_ms}ms</span>
                </div>
              ))}
            </div>
            <div className="flex flex-wrap gap-2">
              {providers.account_health.map((a) => (
                <Badge key={`${a.kind}-${a.name}`} variant={a.status === "healthy" ? "success" : "secondary"}>
                  {a.kind}: {a.status}
                </Badge>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
