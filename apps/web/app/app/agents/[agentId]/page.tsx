import { agentsApi } from "@jkr/sdk";
import { Badge, Card, CardContent, CardDescription, CardHeader, CardTitle } from "@jkr/ui";
import { notFound } from "next/navigation";

import { PublishButton } from "@/components/publish-button";
import { AgentOverviewControls } from "@/components/agent-overview-controls";
import { getActiveWorkspaceContext } from "@/lib/session";

export default async function AgentOverviewPage({ params }: { params: { agentId: string } }) {
  const { workspace, cookieHeader } = await getActiveWorkspaceContext();
  if (!workspace) notFound();

  const agent = await agentsApi.get(workspace.id, params.agentId, { cookieHeader });
  const latest = agent.versions[0];

  return (
    <div className="max-w-4xl space-y-6">
      <AgentOverviewControls workspaceId={workspace.id} agent={agent} />

      <div className="grid gap-4 sm:grid-cols-2">
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Published version</CardDescription>
          </CardHeader>
          <CardContent className="text-lg">
            {agent.published_version_id ? `v${agent.versions.find((v) => v.id === agent.published_version_id)?.version_number}` : "None"}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Latest version</CardDescription>
          </CardHeader>
          <CardContent className="flex items-center gap-2 text-lg">
            v{latest?.version_number}
            {latest ? <Badge variant={latest.status === "published" ? "success" : "secondary"}>{latest.status}</Badge> : null}
          </CardContent>
        </Card>
      </div>

      {latest ? (
        <Card>
          <CardHeader>
            <CardTitle>Latest version summary</CardTitle>
            <CardDescription>Edit under Persona / Voice — publishing locks this version.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div>
              <p className="text-xs font-medium uppercase text-muted-foreground">AI disclosure</p>
              <p className="text-sm">{latest.ai_disclosure_text}</p>
            </div>
            <div>
              <p className="text-xs font-medium uppercase text-muted-foreground">Greeting</p>
              <p className="text-sm">{latest.greeting_text}</p>
            </div>
            {latest.status !== "published" ? (
              <PublishButton workspaceId={workspace.id} agentId={agent.id} versionId={latest.id} />
            ) : null}
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
