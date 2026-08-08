import { workspacesApi } from "@jkr/sdk";
import { EmptyState } from "@jkr/ui";
import { Building2 } from "lucide-react";
import { cookies } from "next/headers";

import { TeamMembers } from "@/components/team-members";
import { getServerSession } from "@/lib/session";

export default async function TeamPage() {
  const me = await getServerSession();
  const cookieHeader = cookies().toString();
  const workspaces = await workspacesApi.list({ cookieHeader }).catch(() => []);
  const active = workspaces.find((w) => w.id === me?.active_workspace_id) ?? workspaces[0];

  if (!active) {
    return (
      <div className="p-8">
        <EmptyState icon={Building2} title="No workspace yet" description="Create a workspace from the dashboard first." />
      </div>
    );
  }

  const members = await workspacesApi.listMembers(active.id, { cookieHeader });

  return (
    <div className="space-y-6 p-8">
      <h1 className="text-2xl font-semibold tracking-tight">Team</h1>
      <TeamMembers workspaceId={active.id} members={members} />
    </div>
  );
}
