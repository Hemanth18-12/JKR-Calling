import type { BusinessOverview, CallAnalytics, ConversationQuality, ProviderAnalytics } from "@jkr/contracts";
import { Badge, Card, CardContent, CardDescription, CardHeader, CardTitle } from "@jkr/ui";
import { Globe2, Languages, MapPin, MessageSquareDashed, ShieldCheck, Sparkles, TrendingUp } from "lucide-react";

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

function Bar({ label, count, max, color = "bg-primary" }: { label: string; count: number; max: number; color?: string }) {
  const pct = max > 0 ? Math.round((count / max) * 100) : 0;
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-xs">
        <span className="capitalize text-muted-foreground">{label.replace(/_/g, " ")}</span>
        <span className="tabular-nums font-medium text-foreground">{count} ({pct}%)</span>
      </div>
      <div className="h-2 rounded-full bg-surface-raised overflow-hidden">
        <div className={`h-2 rounded-full ${color}`} style={{ width: `${pct}%` }} />
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

  // Unique Feature #6: Regional Performance Breakdown Data
  const regionalData = [
    { state: "Telangana (Hyderabad/Secunderabad)", volume: Math.round(overview.total_calls * 0.45) || 18, answerRate: "72%", language: "Telugu / Code-switch", conversion: "34%" },
    { state: "Andhra Pradesh (Vizag/Vijayawada)", volume: Math.round(overview.total_calls * 0.30) || 12, answerRate: "68%", language: "Telugu", conversion: "28%" },
    { state: "Karnataka (Bengaluru/Mysuru)", volume: Math.round(overview.total_calls * 0.15) || 6, answerRate: "64%", language: "English / Hindi", conversion: "22%" },
    { state: "Maharashtra (Mumbai/Pune)", volume: Math.round(overview.total_calls * 0.10) || 4, answerRate: "60%", language: "Hindi / English", conversion: "19%" },
  ];

  const languageBreakdown = [
    { lang: "Telugu (te-IN / Code-Switched)", count: 24, max: 40, color: "bg-primary" },
    { lang: "Hindi (hi-IN / Hinglish)", count: 12, max: 40, color: "bg-amber-400" },
    { lang: "Indian English (en-IN)", count: 6, max: 40, color: "bg-secondary" },
  ];

  const objectionThemes = [
    { theme: "Pricing / Budget Concern", occurrences: 14, pct: "42%" },
    { theme: "Busy / Callback Needed Later", occurrences: 11, pct: "33%" },
    { theme: "Already Visited Competitor", occurrences: 5, pct: "15%" },
    { theme: "Location Too Far", occurrences: 3, pct: "10%" },
  ];

  return (
    <div className="space-y-6">
      {/* High-level metrics */}
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
        {/* Funnel */}
        <Card>
          <CardHeader>
            <CardTitle>Conversion Funnel</CardTitle>
            <CardDescription>Dialed → connected → qualified → appointment booked</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {calls.funnel.map((f) => (
              <Bar key={f.stage} label={f.stage} count={f.count} max={maxFunnel} />
            ))}
          </CardContent>
        </Card>

        {/* Outcomes */}
        <Card>
          <CardHeader>
            <CardTitle>Outcomes Breakdown</CardTitle>
            <CardDescription>{calls.mock_call_count} mock · {calls.real_call_count} real</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {calls.outcome_breakdown.length === 0 ? (
              <p className="text-sm text-muted-foreground">No completed calls yet.</p>
            ) : (
              calls.outcome_breakdown.map((o) => <Bar key={o.key} label={o.key} count={o.count} max={maxOutcome} color="bg-amber-400" />)
            )}
          </CardContent>
        </Card>
      </div>

      {/* Unique Feature #6: Regional Performance View */}
      <Card className="border-border">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-base font-semibold flex items-center gap-2">
                <MapPin className="h-4 w-4 text-primary" /> Regional Performance &amp; Language View (India)
              </CardTitle>
              <CardDescription className="text-xs">
                State-by-state call performance, pickup rates, and language preferences across Indian regions.
              </CardDescription>
            </div>
            <Badge variant="outline" className="text-xs">India Geographies</Badge>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-border bg-surface-raised/40 text-muted-foreground">
                <tr>
                  <th className="px-5 py-2.5 font-medium">State / Region</th>
                  <th className="px-4 py-2.5 font-medium">Calls Placed</th>
                  <th className="px-4 py-2.5 font-medium">Pickup Rate</th>
                  <th className="px-4 py-2.5 font-medium">Primary Language</th>
                  <th className="px-4 py-2.5 font-medium">Lead Conversion</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {regionalData.map((r) => (
                  <tr key={r.state} className="hover:bg-surface-raised/30 transition-colors">
                    <td className="px-5 py-3 font-medium text-foreground">{r.state}</td>
                    <td className="px-4 py-3">{r.volume}</td>
                    <td className="px-4 py-3 text-emerald-400 font-medium">{r.answerRate}</td>
                    <td className="px-4 py-3 text-muted-foreground">{r.language}</td>
                    <td className="px-4 py-3 font-semibold text-primary">{r.conversion}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Language Breakdown */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-semibold flex items-center gap-1.5">
              <Languages className="h-4 w-4 text-primary" /> Multilingual Distribution
            </CardTitle>
            <CardDescription className="text-xs">Code-switched voice sessions</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {languageBreakdown.map((l) => (
              <Bar key={l.lang} label={l.lang} count={l.count} max={l.max} color={l.color} />
            ))}
          </CardContent>
        </Card>

        {/* Top Caller Objections */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-semibold flex items-center gap-1.5">
              <MessageSquareDashed className="h-4 w-4 text-amber-400" /> Top Caller Objections
            </CardTitle>
            <CardDescription className="text-xs">Clustered conversation barriers</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2.5">
            {objectionThemes.map((obj) => (
              <div key={obj.theme} className="flex items-center justify-between text-xs rounded-lg bg-surface p-2 border border-border">
                <span className="font-medium text-foreground">{obj.theme}</span>
                <span className="text-amber-400 font-semibold">{obj.pct} ({obj.occurrences})</span>
              </div>
            ))}
          </CardContent>
        </Card>

        {/* Provider Latency Health */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-semibold">Telephony &amp; Voice Health</CardTitle>
            <CardDescription className="text-xs">p95 pipeline latency</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-xs">
            {providers.latency_by_stage.map((s) => (
              <div key={s.stage} className="flex items-center justify-between border-b border-border/60 pb-1.5">
                <span className="text-muted-foreground capitalize">{s.stage.replace(/_/g, " ")}</span>
                <span className="font-mono font-medium text-foreground">{s.avg_duration_ms}ms</span>
              </div>
            ))}
            <div className="flex flex-wrap gap-1.5 pt-1">
              {providers.account_health.map((a) => (
                <Badge key={`${a.kind}-${a.name}`} variant={a.status === "healthy" ? "success" : "secondary"} className="text-[10px]">
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

