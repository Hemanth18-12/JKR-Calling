import { analyticsApi, contactsApi, workspacesApi } from "@jkr/sdk";
import { Badge, buttonVariants, Card, CardContent, CardDescription, CardHeader, CardTitle, EmptyState } from "@jkr/ui";
import { BarChart3, Plus, Users } from "lucide-react";
import Link from "next/link";
import { cookies } from "next/headers";

import { CreateWorkspaceForm } from "@/components/create-workspace-form";
import { getServerSession } from "@/lib/session";

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

function formatPct(value: number): string {
  return `${Math.round(value * 100)}%`;
}

export default async function DashboardPage() {
  const me = await getServerSession();
  const cookieHeader = cookies().toString();
  const workspaces = await workspacesApi.list({ cookieHeader }).catch(() => []);

  if (!me) return null; // layout already redirects; satisfies TS narrowing

  if (workspaces.length === 0) {
    return (
      <div className="flex min-h-[70vh] items-center justify-center p-8">
        <CreateWorkspaceForm />
      </div>
    );
  }

  const active = workspaces.find((w) => w.id === me.active_workspace_id) ?? workspaces[0];
  if (!active) return null; // unreachable: workspaces.length === 0 already returned above

  const [overview, contacts] = await Promise.all([
    analyticsApi.overview(active.id, { cookieHeader }),
    contactsApi.list(active.id, { cookieHeader }).catch(() => []),
  ]);

  return (
    <div className="space-y-6 p-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Welcome back, {me.user.full_name.split(" ")[0]}</h1>
        <p className="text-muted-foreground">
          {active.name} <Badge variant="outline" className="ml-2">{active.role_key}</Badge>
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Total calls" value={overview.total_calls} />
        <Stat label="Connect rate" value={formatPct(overview.connect_rate)} />
        <Stat label="Appointments booked" value={overview.appointments_booked} />
        <Stat label="Contacts reached" value={overview.contacts_reached} />
        <Stat label="Active campaigns" value={overview.active_campaigns} />
        <Stat label="Pending handoffs" value={overview.pending_handoffs} />
        <Stat label="Revenue (₹)" value={(overview.revenue_paise / 100).toLocaleString("en-IN")} />
        <Stat label="Revenue events" value={overview.revenue_event_count} />
      </div>

      {contacts.length === 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>Get started</CardTitle>
            <CardDescription>No contacts yet in this workspace.</CardDescription>
          </CardHeader>
          <CardContent>
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
          </CardContent>
        </Card>
      ) : overview.total_calls === 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>Get started</CardTitle>
            <CardDescription>No calls yet in this workspace.</CardDescription>
          </CardHeader>
          <CardContent>
            <EmptyState
              icon={BarChart3}
              title="Nothing to show yet"
              description="Create an agent and run a Test Lab call, or launch a campaign — this dashboard and the full analytics page populate from real call outcomes as soon as calls exist."
            />
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="flex items-center justify-between p-5">
            <p className="text-sm text-muted-foreground">See the full funnel, outcome breakdown, and conversation quality metrics.</p>
            <Link href="/app/analytics" className="text-sm font-medium text-primary underline-offset-4 hover:underline">
              Open analytics →
            </Link>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
