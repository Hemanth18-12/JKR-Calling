import { agentsApi, toolsApi } from "@jkr/sdk";
import { EmptyState } from "@jkr/ui";
import { notFound } from "next/navigation";

import { AgentToolsEditor } from "@/components/agent-tools-editor";
import { getActiveWorkspaceContext } from "@/lib/session";

export default async function AgentToolsTabPage({ params }: { params: { agentId: string } }) {
  const { workspace, cookieHeader } = await getActiveWorkspaceContext();
  if (!workspace) notFound();

  const agent = await agentsApi.get(workspace.id, params.agentId, { cookieHeader });
  const versionId = agent.versions[0]?.id;
  if (!versionId) {
    return (
      <div className="p-8">
        <EmptyState title="No version yet" description="This agent has no versions." />
      </div>
    );
  }

  const tools = await toolsApi.listAgentTools(workspace.id, versionId, { cookieHeader });

  return (
    <div className="p-8">
      <AgentToolsEditor workspaceId={workspace.id} agentVersionId={versionId} initialTools={tools} />
    </div>
  );
}
