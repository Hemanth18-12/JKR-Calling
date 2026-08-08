import { agentsApi } from "@jkr/sdk";
import { notFound } from "next/navigation";

import { AgentTabs } from "@/components/agent-tabs";
import { getActiveWorkspaceContext } from "@/lib/session";

export default async function AgentLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: { agentId: string };
}) {
  const { workspace, cookieHeader } = await getActiveWorkspaceContext();
  if (!workspace) notFound();

  const agent = await agentsApi.get(workspace.id, params.agentId, { cookieHeader }).catch(() => null);
  if (!agent) notFound();

  return (
    <div>
      <AgentTabs agentId={agent.id} agentName={agent.name} status={agent.status} />
      <div className="p-8">{children}</div>
    </div>
  );
}
