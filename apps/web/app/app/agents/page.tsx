import { agentsApi, workspacesApi } from "@jkr/sdk";
import { Badge, buttonVariants, Card, CardContent, EmptyState } from "@jkr/ui";
import { Bot, Plus } from "lucide-react";
import { cookies } from "next/headers";
import Link from "next/link";

import { getServerSession } from "@/lib/session";
import { AgentPromptCreator } from "@/components/agent-prompt-creator";

const STATUS_VARIANT: Record<string, "success" | "secondary" | "warning"> = {
  active: "success",
  draft: "secondary",
  archived: "warning",
};

export default async function AgentsPage() {
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

  const agents = await agentsApi.list(active.id, { cookieHeader }).catch(() => []);

  return (
    <div className="space-y-8 p-6 sm:p-8 max-w-7xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground sm:text-3xl">Voice AI Assistants</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Create, train, and manage multilingual voice agents for your business calls.
        </p>
      </div>

      {/* Pattern 5b: Describe to create box */}
      <AgentPromptCreator workspaceId={active.id} />

      {/* Existing Agent List Section */}
      <div className="space-y-4 pt-2">
        <div className="flex items-center justify-between border-b border-border/40 pb-3">
          <div>
            <h2 className="text-lg font-bold tracking-tight text-foreground">My Voice AI Assistants</h2>
            <p className="text-xs text-muted-foreground">Active calling assistants in this workspace</p>
          </div>
          <Link href="/app/agents/new" className={buttonVariants({ variant: "outline", size: "sm" })}>
            <Plus className="mr-1 h-3.5 w-3.5" /> Manual Wizard
          </Link>
        </div>

      {agents.length === 0 ? (
        <EmptyState
          icon={Bot}
          title="No agents yet"
          description="Create your first agent from a persona template."
          action={
            <Link href="/app/agents/new" className={buttonVariants({ variant: "gradient" })}>
              <Plus className="h-4 w-4" /> New agent
            </Link>
          }
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {agents.map((agent) => (
            <Link key={agent.id} href={`/app/agents/${agent.id}`}>
              <Card className="h-full transition-colors hover:border-primary/50">
                <CardContent className="p-5">
                  <div className="mb-2 flex items-center justify-between">
                    <Bot className="h-5 w-5 text-primary" />
                    <Badge variant={STATUS_VARIANT[agent.status] ?? "secondary"}>{agent.status}</Badge>
                  </div>
                  <h3 className="font-semibold">{agent.name}</h3>
                  <p className="text-sm text-muted-foreground">{agent.business_identity}</p>
                  <p className="mt-2 font-mono text-xs text-muted-foreground">{agent.primary_language}</p>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
      </div>
    </div>
  );
}
