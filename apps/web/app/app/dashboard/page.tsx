import {
  agentsApi,
  analyticsApi,
  callsApi,
  campaignsApi,
  contactsApi,
  knowledgeApi,
  workspacesApi,
} from "@jkr/sdk";
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
  Calendar,
  CheckCircle2,
  Clock,
  Coins,
  ExternalLink,
  Flame,
  Handshake,
  Megaphone,
  Phone,
  PhoneCall,
  PhoneIncoming,
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
import { StartTourButton } from "@/components/guided-tour";
import { DashboardStatCards } from "@/components/dashboard/dashboard-stat-cards";
import { DashboardLiveTicker } from "@/components/dashboard/dashboard-live-ticker";
import { SetupChecklist } from "@/components/dashboard/dashboard-checklist";

function formatPct(value: number): string {
  return `${Math.round(value * 100)}%`;
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

  const [overview, contacts, calls, agents, campaigns, docs] = await Promise.all([
    analyticsApi.overview(active.id, { cookieHeader }).catch(() => defaultOverview),
    contactsApi.list(active.id, { cookieHeader }).catch(() => []),
    callsApi.list(active.id, undefined, { cookieHeader }).catch(() => []),
    agentsApi.list(active.id, { cookieHeader }).catch(() => []),
    campaignsApi.list(active.id, { cookieHeader }).catch(() => []),
    knowledgeApi.listDocuments(active.id, { cookieHeader }).catch(() => []),
  ]);

  // Cost-per-outcome ROI Calculation
  const estimatedCostPerCallPaise = 150; // ~₹1.50 per AI call
  const totalSpendRupees = Math.round((overview.total_calls * estimatedCostPerCallPaise) / 100);
  const costPerAppointment =
    overview.appointments_booked > 0
      ? `₹${Math.round(totalSpendRupees / overview.appointments_booked)}`
      : overview.total_calls > 0
      ? `₹${totalSpendRupees}`
      : "₹0";

  const humanCostBenchmark = "₹180 to ₹250";
  const recentCalls = calls.slice(0, 8);

  return (
    <div className="space-y-6 p-4 sm:p-8 max-w-7xl mx-auto">
      {/* Page Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between border-b border-border/60 pb-5">
        <div>
          <h1 className="font-display text-2xl sm:text-3xl font-bold tracking-tight text-foreground">
            Welcome back, {me.user.full_name}
          </h1>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <span className="font-medium text-foreground">{active.name}</span>
            <span>·</span>
            <span className="uppercase tracking-wider font-mono text-[11px] bg-surface-raised px-2 py-0.5 rounded border border-border/80">
              {active.role_key}
            </span>
            <span>·</span>
            <span className="flex items-center gap-1 text-muted-foreground">
              <Clock className="h-3 w-3" />
              <span>IST Calling Hours Active</span>
            </span>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <StartTourButton pageId="dashboard" label="Guide Tour" variant="outline" size="sm" />
          <Link href="/app/campaigns/new" className={buttonVariants({ variant: "outline", size: "sm" })}>
            <Megaphone className="h-3.5 w-3.5 mr-1" />
            New Campaign
          </Link>
          <Link href="/app/agents" className={buttonVariants({ variant: "default", size: "sm" })}>
            <Bot className="h-3.5 w-3.5 mr-1" />
            Voice Agents
          </Link>
        </div>
      </div>

      {/* Setup Checklist for onboarding workspaces */}
      <SetupChecklist
        hasAgents={agents.length > 0}
        hasKnowledge={docs.length > 0}
        hasCalls={calls.length > 0}
        hasCampaigns={campaigns.length > 0}
      />

      {/* Real-Time Live Ticker */}
      <DashboardLiveTicker />

      {/* Top Row: Outcome-First Hero KPI Cards */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <div>
            <h2 className="font-display text-sm font-semibold text-foreground">Outcome Performance</h2>
            <p className="text-xs text-muted-foreground">Key conversion metrics for this workspace</p>
          </div>
        </div>

        <DashboardStatCards
          items={[
            {
              key: "appointments_booked",
              label: "Appointments Booked",
              rawValue: overview.appointments_booked,
              iconName: "calendar",
              accent: "primary",
              badge: "Goal Outcome",
              subtext: `${costPerAppointment} estimated acquisition cost`,
            },
            {
              key: "connect_rate",
              label: "Connect Rate",
              rawValue: overview.connect_rate,
              isPct: true,
              iconName: "phone",
              accent: "emerald",
              badge: "Telephony",
              subtext: `${overview.connected_calls} of ${overview.total_calls} connected`,
            },
            {
              key: "revenue_event_count",
              label: "Revenue Events",
              rawValue: overview.revenue_event_count,
              iconName: "check",
              accent: "amber",
              badge: "Qualified",
              subtext: "Conversions & verified intents",
            },
            {
              key: "revenue_paise",
              label: "Revenue Generated",
              rawValue: Math.round(overview.revenue_paise / 100),
              isRevenue: true,
              iconName: "coins",
              accent: "primary",
              badge: "Attributed",
              subtext: "Total recorded pipeline value",
            },
          ]}
        />
      </div>

      {/* Secondary Operational Metrics Grid */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Card className="border-border/80 bg-surface shadow-subtle">
          <CardContent className="p-4 flex items-center justify-between">
            <div>
              <p className="text-xs text-muted-foreground font-medium">Total Calls Dialed</p>
              <p className="font-display text-xl font-bold tabular-nums text-foreground mt-0.5">
                {overview.total_calls.toLocaleString("en-IN")}
              </p>
            </div>
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-surface-raised border border-border text-foreground/80">
              <Phone className="h-4 w-4" />
            </div>
          </CardContent>
        </Card>

        <Card className="border-border/80 bg-surface shadow-subtle">
          <CardContent className="p-4 flex items-center justify-between">
            <div>
              <p className="text-xs text-muted-foreground font-medium">Contacts Reached</p>
              <p className="font-display text-xl font-bold tabular-nums text-foreground mt-0.5">
                {overview.contacts_reached.toLocaleString("en-IN")}
              </p>
            </div>
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-surface-raised border border-border text-foreground/80">
              <Users className="h-4 w-4" />
            </div>
          </CardContent>
        </Card>

        <Card className="border-border/80 bg-surface shadow-subtle">
          <CardContent className="p-4 flex items-center justify-between">
            <div>
              <p className="text-xs text-muted-foreground font-medium">Active Campaigns</p>
              <p className="font-display text-xl font-bold tabular-nums text-foreground mt-0.5">
                {overview.active_campaigns}
              </p>
            </div>
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-surface-raised border border-border text-foreground/80">
              <Megaphone className="h-4 w-4" />
            </div>
          </CardContent>
        </Card>

        <Card className="border-border/80 bg-surface shadow-subtle">
          <CardContent className="p-4 flex items-center justify-between">
            <div>
              <p className="text-xs text-muted-foreground font-medium">Pending Handoffs</p>
              <p className="font-display text-xl font-bold tabular-nums text-foreground mt-0.5">
                {overview.pending_handoffs}
              </p>
            </div>
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-surface-raised border border-border text-foreground/80">
              <Handshake className="h-4 w-4" />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Unit Economics Comparison Banner */}
      <Card id="tour-roi-ticker" className="border-border/80 bg-surface">
        <CardContent className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 p-5">
          <div className="flex items-center gap-3.5">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 border border-primary/20 text-primary">
              <TrendingUp className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold uppercase tracking-wider text-primary">
                  Unit Acquisition Economics
                </span>
                <span className="text-[10px] text-muted-foreground font-mono bg-surface-raised px-1.5 py-0.5 rounded border border-border/60">
                  Telemetry ROI
                </span>
              </div>
              <p className="text-sm font-medium text-foreground mt-0.5">
                AI Acquisition Cost: <strong className="text-foreground">{costPerAppointment}</strong> per booked appointment
              </p>
            </div>
          </div>
          <div className="rounded-lg border border-border/80 bg-surface-raised px-3.5 py-2 text-xs text-muted-foreground">
            <p>Human SDR Cost: <strong className="text-foreground">{humanCostBenchmark}</strong></p>
            <p className="text-[11px] text-emerald-400 font-medium mt-0.5">Estimated 75% to 85% savings per qualified lead</p>
          </div>
        </CardContent>
      </Card>

      {/* Recent Call Outcomes Table */}
      <Card id="tour-recent-calls" className="border-border/80 bg-surface shadow-subtle">
        <CardHeader className="flex flex-row items-center justify-between pb-3 border-b border-border/60">
          <div>
            <CardTitle className="text-base font-semibold">Recent Call Outcomes</CardTitle>
            <CardDescription className="text-xs">Latest conversation recordings and caller dispositions</CardDescription>
          </div>
          <Link href="/app/calls" className="text-xs font-semibold text-primary hover:underline flex items-center gap-1">
            <span>View all calls</span>
            <ExternalLink className="h-3 w-3" />
          </Link>
        </CardHeader>
        <CardContent className="p-0">
          {recentCalls.length === 0 ? (
            <div className="p-8">
              <EmptyState
                icon={Phone}
                title="No call outcomes recorded yet"
                description="Place a test call or launch a campaign to generate call dispositions."
                action={
                  <Link href="/app/agents" className={buttonVariants({ variant: "outline", size: "sm" })}>
                    <Bot className="h-3.5 w-3.5 mr-1" />
                    Open Test Lab
                  </Link>
                }
              />
            </div>
          ) : (
            <div className="divide-y divide-border/60">
              {recentCalls.map((c) => (
                <Link
                  key={c.call_id}
                  href={`/app/calls/${c.call_id}`}
                  className="flex items-center justify-between px-5 py-3 text-sm transition-colors hover:bg-surface-raised"
                >
                  <div className="flex items-center gap-3">
                    <div
                      className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border ${
                        c.campaign_id
                          ? "border-primary/20 bg-primary/10 text-primary"
                          : "border-border bg-surface-raised text-muted-foreground"
                      }`}
                    >
                      {c.campaign_id ? <Megaphone className="h-3.5 w-3.5" /> : <Phone className="h-3.5 w-3.5" />}
                    </div>
                    <div>
                      <p className="font-medium text-foreground text-xs sm:text-sm">
                        {c.contact_name ?? "Direct Test Call"}
                      </p>
                      <p className="text-[11px] text-muted-foreground flex items-center gap-1.5 mt-0.5">
                        <span>
                          {c.started_at
                            ? new Date(c.started_at).toLocaleTimeString("en-IN", {
                                hour: "2-digit",
                                minute: "2-digit",
                                timeZone: "Asia/Kolkata",
                              })
                            : "Recently"}
                        </span>
                        {c.duration_seconds != null ? (
                          <>
                            <span>·</span>
                            <span className="font-mono tabular-nums">{c.duration_seconds}s</span>
                          </>
                        ) : null}
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    {c.outcome_category ? (
                      <Badge variant="outline" className="text-[11px] capitalize">
                        {c.outcome_category.replace(/_/g, " ")}
                      </Badge>
                    ) : null}
                    <Badge variant={CALL_STATUS_VARIANT[c.status] ?? "secondary"} className="text-[11px]">
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
