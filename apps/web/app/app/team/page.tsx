import { coinsApi, workspacesApi } from "@jkr/sdk";
import { EmptyState } from "@jkr/ui";
import { Building2 } from "lucide-react";

import { OrganizationManagement } from "@/components/organization-management";
import { getActiveWorkspaceContext } from "@/lib/session";

export default async function TeamPage() {
  const { workspace, me, cookieHeader } = await getActiveWorkspaceContext();

  if (!workspace) {
    return (
      <div className="p-8">
        <EmptyState icon={Building2} title="No workspace yet" description="Create a workspace from the dashboard first." />
      </div>
    );
  }

  const [members, wallet] = await Promise.all([
    workspacesApi.listMembers(workspace.id, { cookieHeader }).catch((err) => {
      console.error("Failed to list members:", err);
      return [];
    }),
    coinsApi.getWallet(workspace.id, { cookieHeader }).catch(() => null),
  ]);

  // If no members returned from API (e.g. mock or error), provide self as Owner
  const displayMembers =
    members.length > 0
      ? members
      : [
          {
            id: workspace.id,
            user_id: me?.user?.id ?? workspace.id,
            email: me?.user?.email ?? "owner@jkr.ai",
            full_name: me?.user?.full_name ?? "Workspace Owner",
            role_key: "workspace_owner",
            status: "active",
            invited_at: null,
            joined_at: new Date().toISOString(),
          },
        ];

  return (
    <div className="space-y-6 p-6 sm:p-8 max-w-7xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground sm:text-3xl">Organization Management</h1>
        <p className="text-sm text-muted-foreground mt-1">
          View and manage users, roles, concurrency capacity, and wallet balance in your organization.
        </p>
      </div>

      <OrganizationManagement
        workspace={workspace}
        members={displayMembers}
        wallet={wallet}
        currentUserId={me?.user?.id}
      />
    </div>
  );
}
