import { agentsApi } from "@jkr/sdk";
import { EmptyState } from "@jkr/ui";
import { notFound } from "next/navigation";

import { PersonaEditor } from "@/components/persona-editor";
import { getActiveWorkspaceContext } from "@/lib/session";

export default async function AgentPersonaPage({
  params,
  searchParams,
}: {
  params: { agentId: string };
  searchParams: { version?: string };
}) {
  const { workspace, cookieHeader } = await getActiveWorkspaceContext();
  if (!workspace) notFound();

  const agent = await agentsApi.get(workspace.id, params.agentId, { cookieHeader });
  const versionId = searchParams.version ?? agent.versions[0]?.id;
  if (!versionId) {
    return <EmptyState title="No version yet" description="This agent has no versions." />;
  }

  const version = await agentsApi.getVersion(workspace.id, agent.id, versionId, { cookieHeader });

  return <PersonaEditor workspaceId={workspace.id} agentId={agent.id} version={version} />;
}
