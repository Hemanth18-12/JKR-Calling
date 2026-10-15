import { agentsApi, knowledgeApi } from "@jkr/sdk";
import { notFound } from "next/navigation";

import { KnowledgeDocuments } from "@/components/knowledge-documents";
import { getActiveWorkspaceContext } from "@/lib/session";

export default async function AgentKnowledgeTabPage(props: {
  params: Promise<{ agentId: string }> | { agentId: string };
}) {
  const resolvedParams = await Promise.resolve(props.params);
  const { workspace, cookieHeader } = await getActiveWorkspaceContext();
  if (!workspace) notFound();

  const [documents, agents] = await Promise.all([
    knowledgeApi.listDocuments(workspace.id, resolvedParams.agentId, { cookieHeader }),
    agentsApi.list(workspace.id, { cookieHeader }),
  ]);

  return (
    <div className="space-y-6">
      <KnowledgeDocuments
        workspaceId={workspace.id}
        documents={documents}
        agents={agents}
        initialAgentId={resolvedParams.agentId}
      />
    </div>
  );
}
