import { agentsApi } from "@jkr/sdk";
import { notFound } from "next/navigation";

import { getActiveWorkspaceContext } from "@/lib/session";
import { VersionsList } from "@/components/versions-list";

export default async function AgentVersionsPage({ params }: { params: { agentId: string } }) {
  const { workspace, cookieHeader } = await getActiveWorkspaceContext();
  if (!workspace) notFound();

  const agent = await agentsApi.get(workspace.id, params.agentId, { cookieHeader });
  return <VersionsList workspaceId={workspace.id} agentId={agent.id} versions={agent.versions} />;
}
