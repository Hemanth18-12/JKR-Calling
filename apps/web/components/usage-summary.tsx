import type { UsageSummary } from "@jkr/contracts";
import { Badge, Card, CardContent, CardDescription, CardHeader, CardTitle, EmptyState } from "@jkr/ui";
import { Gauge } from "lucide-react";

export function UsageSummaryView({ usage }: { usage: UsageSummary }) {
  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-3">
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Total calls</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-semibold tabular-nums">{usage.total_calls}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Total call time</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-semibold tabular-nums">{Math.round(usage.total_call_seconds / 60)} min</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Metered event types</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-semibold tabular-nums">{usage.usage_by_type.length}</p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Usage by type</CardTitle>
          <CardDescription>Real events logged as calls complete — see conversation_engine.py::end_session.</CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          {usage.usage_by_type.length === 0 ? (
            <div className="p-5">
              <EmptyState icon={Gauge} title="No usage yet" description="Run a call to see real usage events here." />
            </div>
          ) : (
            <div className="divide-y divide-border">
              {usage.usage_by_type.map((u) => (
                <div key={u.event_type} className="flex items-center justify-between px-5 py-3 text-sm">
                  <span className="capitalize">{u.event_type.replace(/_/g, " ")}</span>
                  <span className="tabular-nums text-muted-foreground">
                    {u.total_quantity} {u.unit} · {u.event_count} event{u.event_count === 1 ? "" : "s"}
                  </span>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Campaign budgets</CardTitle>
          <CardDescription>Enforced by the campaign safety gate&apos;s check #9 on every dispatch attempt.</CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          {usage.campaign_budgets.length === 0 ? (
            <p className="p-5 text-sm text-muted-foreground">No campaign has a daily budget configured.</p>
          ) : (
            <div className="divide-y divide-border">
              {usage.campaign_budgets.map((b) => {
                const pct = b.daily_budget_paise > 0 ? Math.min(100, Math.round((b.spent_today_paise / b.daily_budget_paise) * 100)) : 0;
                return (
                  <div key={b.campaign_id} className="px-5 py-3 text-sm">
                    <div className="mb-1 flex items-center justify-between">
                      <span>{b.campaign_name}</span>
                      <Badge variant={pct >= 100 ? "danger" : pct >= 80 ? "warning" : "secondary"}>
                        ₹{(b.spent_today_paise / 100).toFixed(2)} / ₹{(b.daily_budget_paise / 100).toFixed(2)} today
                      </Badge>
                    </div>
                    <div className="h-1.5 rounded-full bg-surface-raised">
                      <div className="h-1.5 rounded-full bg-primary" style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
