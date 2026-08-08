import { notFound } from "next/navigation";

import { LiveRealCallCard } from "@/components/live-real-call-card";
import { TestLabChat } from "@/components/test-lab-chat";
import { getActiveWorkspaceContext } from "@/lib/session";

export default async function AgentTestLabTabPage({ params }: { params: { agentId: string } }) {
  const { workspace } = await getActiveWorkspaceContext();
  if (!workspace) notFound();

  return (
    <div className="space-y-6">
      <TestLabChat workspaceId={workspace.id} agentId={params.agentId} />
      <LiveRealCallCard workspaceId={workspace.id} agentId={params.agentId} />
    </div>
  );
}
