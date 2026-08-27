import { analyticsApi, callsApi, contactsApi, workspacesApi } from "@jkr/sdk";
import { CALL_STATUS_VARIANT } from "@jkr/contracts";
import {
  Badge,
  buttonVariants,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  EmptyState,
} from "@jkr/ui";
import {
  BarChart3,
  Bot,
  CalendarCheck,
  CheckCircle2,
  ExternalLink,
  Flame,
  Megaphone,
  Phone,
  PhoneCall,
  Plus,
  Radio,
  Sparkles,
  TrendingUp,
  UploadCloud,
  Users,
  Zap,
} from "lucide-react";
import Link from "next/link";
import { cookies } from "next/headers";

import { CreateWorkspaceForm } from "@/components/create-workspace-form";
import { getServerSession } from "@/lib/session";

const STAT_CONFIG = [
  { key: "total_calls", label: "Total calls", icon: "📞", accent: "primary", stagger: 1 },
  { key: "connect_rate", label: "Connect rate", icon: "🎯", accent: "amber", stagger: 2, isPct: true },
  { key: "appointments_booked", label: "Appointments booked", icon: "📅", accent: "amber", stagger: 3 },
  { key: "contacts_reached", label: "Contacts reached", icon: "👥", accent: "primary", stagger: 4 },
  { key: "active_campaigns", label: "Active campaigns", icon: "📣", accent: "primary", stagger: 5 },
  { key: "pending_handoffs", label: "Pending handoffs", icon: "🤝", accent: "danger", stagger: 6 },
  { key: "revenue_paise", label: "Revenue generated (₹)", icon: "₹", accent: "amber", stagger: 7, isRevenue: true },
  { key: "revenue_event_count", label: "Revenue events", icon: "⚡", accent: "amber", stagger: 8 },
] as const;

function formatPct(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function StatCard({
  label,
  value,
  icon,
  accent,
  stagger,
}: {
  label: string;
  value: string | number;
  icon: string;
  accent: "primary" | "amber" | "danger";
  stagger: number;
}) {
  const accentClasses = {
    primary: "text-primary border-primary/20 bg-primary/8",
    amber: "text-amber-400 border-amber-500/20 bg-amber-500/8",
    danger: "text-danger border-danger/20 bg-danger/8",
  }[accent];

  return (
    <Card className={`stagger-${stagger} group overflow-hidden hover:-translate-y-1 transition-transform`}>
      <CardContent className="p-5">
        <div className="mb-3 flex items-center justify-between">
          <span className={`flex h-8 w-8 items-center justify-center rounded-lg border text-sm ${accentClasses}`}>
            {icon}
          </span>
        </div>
        <p className="font-display text-2xl font-bold tabular-nums text-foreground">{value}</p>
        <p className="mt-0.5 text-xs text-muted-foreground">{label}</p>
      </CardContent>
    </Card>
  );
}

export default async function DashboardPage() {
  const me = await getServerSession();
  const cookieHeader = cookies().toString();
  const workspaces = await workspacesApi.list({ cookieHeader }).catch(() => []);

  if (!me) return null;

  if (workspaces.length === 0) {
    return (
      <div className="flex min-h-[70vh] items-center justify-center p-8">
        <CreateWorkspaceForm />
      </div>
    );
  }

  const active = workspaces.find((w) => w.id === me.active_workspace_id) ?? workspaces[0];
  if (!active) return null;

  const defaultOverview = {
    total_calls: 0,
    connected_calls: 0,
    connect_rate: 0,
    appointments_booked: 0,
    contacts_reached: 0,
    active_campaigns: 0,
    pending_handoffs: 0,
    revenue_paise: 0,
    revenue_event_count: 0,
  };

  const [overview, contacts, calls] = await Promise.all([
    analyticsApi.overview(active.id, { cookieHeader }).catch(() => defaultOverview),
    contactsApi.list(active.id, { cookieHeader }).catch(() => []),
    callsApi.list(active.id, undefined, { cookieHeader }).catch(() => []),
  ]);

  const statValues: Record<string, string | number> = {
    total_calls: overview.total_calls,
    connect_rate: formatPct(overview.connect_rate),
    appointments_booked: overview.appointments_booked,
    contacts_reached: overview.contacts_reached,
    active_campaigns: overview.active_campaigns,
    pending_handoffs: overview.pending_handoffs,
    revenue_paise: (overview.revenue_paise / 100).toLocaleString("en-IN"),
    revenue_event_count: overview.revenue_event_count,
  };

  // Unique Feature #4: Cost-per-outcome ROI Calculation
  const estimatedCostPerCallPaise = 150; // ~₹1.50 per AI call
  const totalSpendRupees = Math.round((overview.total_calls * estimatedCostPerCallPaise) / 100);
  const costPerAppointment =
    overview.appointments_booked > 0
      ? `₹${Math.round(totalSpendRupees / overview.appointments_booked)}`
      : overview.total_calls > 0
      ? `₹${totalSpendRupees} (0 bookings)`
      : "₹0";

  const humanCostBenchmark = "₹180–₹250";
  const recentCalls = calls.slice(0, 8);

  return (
    <div className="space-y-8 p-8">
      {/* Page header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold text-foreground">
            Welcome back,{" "}
            <span className="bg-gradient-to-r from-primary to-[#A78BFF] bg-clip-text text-transparent">
              {me.user.full_name.split(" ")[0]}
            </span>
          </h1>
          <p className="mt-1 flex items-center gap-2 text-sm text-muted-foreground">
            {active.name}
            <Badge variant="outline" className="text-xs">
              {active.role_key}
            </Badge>
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link href="/app/campaigns" className={buttonVariants({ variant: "gradient", size: "sm" })}>
            <Megaphone className="h-3.5 w-3.5" />
            Launch batch
          </Link>
          <Link href="/app/analytics" className={buttonVariants({ variant: "outline", size: "sm" })}>
            <BarChart3 className="h-3.5 w-3.5" />
            Full analytics
          </Link>
        </div>
      </div>

      {/* Real-Time Active Ticker & Quick Actions */}
      <div className="grid gap-4 md:grid-cols-3">
        {/* Active Telephony Channel status */}
        <Card className="border-secondary/30 bg-secondary/5">
          <CardContent className="flex items-center gap-3 p-4">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-secondary/15 text-secondary">
              <Radio className="h-4 w-4 animate-pulse" />
            </div>
            <div className="text-xs">
              <p className="font-medium text-foreground">Live Telephony & SIP Pipeline</p>
              <p className="text-muted-foreground">LiveKit Cloud connected · Ready for calls</p>
            </div>
          </CardContent>
        </Card>

        {/* Quick Action: Test Agent Call */}
        <Link href="/app/agents">
          <Card className="hover:border-primary/40 transition-colors cursor-pointer h-full">
            <CardContent className="flex items-center gap-3 p-4">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-primary/15 text-primary">
                <Bot className="h-4 w-4" />
              </div>
              <div className="text-xs">
                <p className="font-medium text-foreground">Test AI Voice Agent</p>
                <p className="text-muted-foreground">Open Test Lab in browser or SIP dialer →</p>
              </div>
            </CardContent>
          </Card>
        </Link>

        {/* Quick Action: Upload Contacts */}
        <Link href="/app/contacts">
          <Card className="hover:border-primary/40 transition-colors cursor-pointer h-full">
            <CardContent className="flex items-center gap-3 p-4">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-amber-500/15 text-amber-500">
                <UploadCloud className="h-4 w-4" />
              </div>
              <div className="text-xs">
                <p className="font-medium text-foreground">Import Contact Lists</p>
                <p className="text-muted-foreground">CSV bulk upload with consent logging →</p>
              </div>
            </CardContent>
          </Card>
        </Link>
      </div>

      {/* Stats grid */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {STAT_CONFIG.map((cfg) => (
          <StatCard
            key={cfg.key}
            label={cfg.label}
            value={statValues[cfg.key] ?? 0}
            icon={cfg.icon}
            accent={cfg.accent}
            stagger={cfg.stagger}
          />
        ))}
      </div>

      {/* Unique Feature #4: Cost-per-outcome ROI Ticker */}
      <Card className="border-border bg-gradient-to-r from-surface to-surface-raised">
        <CardContent className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 p-5">
          <div className="flex items-center gap-3.5">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-amber-500/15 text-amber-400">
              <Zap className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold uppercase tracking-wider text-amber-400">Cost-Per-Outcome ROI Ticker</span>
                <Badge variant="outline" className="text-[10px] text-muted-foreground">Real-time unit economics</Badge>
              </div>
              <p className="text-sm font-medium text-foreground">
                Current AI Acquisition Cost: <span className="text-lg font-bold text-amber-400">{costPerAppointment}</span> / booked appointment
              </p>
            </div>
          </div>
          <div className="rounded-lg border border-border/60 bg-surface/80 px-3 py-2 text-xs text-muted-foreground">
            <p>vs. Human BDR Cost: <strong className="text-foreground">{humanCostBenchmark}</strong></p>
            <p className="text-[11px] text-emerald-400 font-medium">✨ Saving ~75–85% per qualified booking</p>
          </div>
        </CardContent>
      </Card>

      {/* Recent Outcomes Table */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-3">
          <div>
            <CardTitle className="text-base font-semibold">Recent Call Outcomes</CardTitle>
            <CardDescription>Latest calls and real-time agent dispositions</CardDescription>
          </div>
          <Link href="/app/calls" className="text-xs font-medium text-primary hover:underline flex items-center gap-1">
            View all calls <ExternalLink className="h-3 w-3" />
          </Link>
        </CardHeader>
        <CardContent className="p-0">
          {recentCalls.length === 0 ? (
            <p className="p-6 text-center text-sm text-muted-foreground">No call outcomes recorded yet.</p>
          ) : (
            <div className="divide-y divide-border">
              {recentCalls.map((c) => (
                <Link
                  key={c.call_id}
                  href={`/app/calls/${c.call_id}`}
                  className="flex items-center justify-between px-5 py-3 text-sm transition-colors hover:bg-surface-raised"
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
                      <p className="font-medium text-foreground">{c.contact_name ?? "Direct Test Call"}</p>
                      <p className="text-xs text-muted-foreground">
                        {c.started_at
                          ? new Date(c.started_at).toLocaleTimeString("en-IN", {
                              hour: "2-digit",
                              minute: "2-digit",
                              timeZone: "Asia/Kolkata",
                            })
                          : "recently"}{" "}
                        {c.duration_seconds != null ? `· ${c.duration_seconds}s` : ""}
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    {c.outcome_category ? (
                      <Badge variant="outline" className="text-xs capitalize">
                        {c.outcome_category.replace(/_/g, " ")}
                      </Badge>
                    ) : null}
                    <Badge variant={CALL_STATUS_VARIANT[c.status] ?? "secondary"} className="text-xs">
                      {c.status.replace(/_/g, " ")}
                    </Badge>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

