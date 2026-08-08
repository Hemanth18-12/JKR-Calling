import { agentsApi, workspacesApi } from "@jkr/sdk";
import { EmptyState } from "@jkr/ui";
import { Bot } from "lucide-react";
import { cookies } from "next/headers";

import { NewAgentForm } from "@/components/new-agent-form";
import { getServerSession } from "@/lib/session";

export default async function NewAgentPage() {
  const me = await getServerSession();
  const cookieHeader = cookies().toString();
  const workspaces = await workspacesApi.list({ cookieHeader }).catch(() => []);
  const active = workspaces.find((w) => w.id === me?.active_workspace_id) ?? workspaces[0];

  if (!active) {
    return (
      <div className="p-8">
        <EmptyState icon={Bot} title="No workspace yet" description="Create a workspace from the dashboard first." />
      </div>
    );
  }

  const templates = await agentsApi.personaTemplates(active.id, { cookieHeader });

  return (
    <div className="p-8">
      <NewAgentForm workspaceId={active.id} templates={templates} />
    </div>
  );
}
