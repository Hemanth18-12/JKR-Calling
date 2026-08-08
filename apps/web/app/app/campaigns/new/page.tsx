import { agentsApi } from "@jkr/sdk";
import { notFound } from "next/navigation";

import { NewCampaignForm } from "@/components/new-campaign-form";
import { getActiveWorkspaceContext } from "@/lib/session";

export default async function NewCampaignPage() {
  const { workspace, cookieHeader } = await getActiveWorkspaceContext();
  if (!workspace) notFound();

  const agents = await agentsApi.list(workspace.id, { cookieHeader });
  const published = agents.filter((a) => a.published_version_id !== null);

  return (
    <div className="p-8">
      <NewCampaignForm workspaceId={workspace.id} agents={published} />
    </div>
  );
}
