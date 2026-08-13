import { analyticsApi, contactsApi, workspacesApi } from "@jkr/sdk";
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
import { BarChart3, Plus, TrendingUp, Users } from "lucide-react";
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
  { key: "revenue_paise", label: "Revenue (₹)", icon: "₹", accent: "amber", stagger: 7, isRevenue: true },
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
    <Card className={`stagger-${stagger} group overflow-hidden hover:-translate-y-1`}>
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

  const [overview, contacts] = await Promise.all([
    analyticsApi.overview(active.id, { cookieHeader }).catch(() => defaultOverview),
    contactsApi.list(active.id, { cookieHeader }).catch(() => []),
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

  return (
    <div className="space-y-8 p-8">
      {/* Page header */}
      <div className="flex items-start justify-between">
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
        <Link href="/app/analytics" className={buttonVariants({ variant: "outline", size: "sm" })}>
          <BarChart3 className="h-3.5 w-3.5" />
          Full analytics
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

      {/* Empty state / CTA */}
      {contacts.length === 0 ? (
        <EmptyState
          icon={Users}
          title="Add your first contacts"
          description="You'll need at least one contact before an agent can call anyone — add contacts, then record consent, before creating a campaign."
          action={
            <Link href="/app/contacts" className={buttonVariants({ variant: "gradient" })}>
              <Plus className="h-4 w-4" /> Add contacts
            </Link>
          }
        />
      ) : overview.total_calls === 0 ? (
        <EmptyState
          icon={BarChart3}
          title="Nothing to show yet"
          description="Create an agent and run a Test Lab call, or launch a campaign — this dashboard populates from real call outcomes."
        />
      ) : (
        <Card>
          <CardContent className="flex items-center justify-between p-5">
            <div className="flex items-center gap-3">
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-amber-500/10">
                <TrendingUp className="h-4 w-4 text-amber-400" />
              </div>
              <p className="text-sm text-muted-foreground">
                See the full funnel, outcome breakdown, and conversation quality metrics.
              </p>
            </div>
            <Link
              href="/app/analytics"
              className="text-sm font-medium text-primary underline-offset-4 hover:underline"
            >
              Open analytics →
            </Link>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
