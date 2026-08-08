import { callsApi } from "@jkr/sdk";
import { notFound } from "next/navigation";

import { LiveCallConsole } from "@/components/live-call-console";
import { getActiveWorkspaceContext } from "@/lib/session";

export default async function LiveCallsPage() {
  const { workspace, cookieHeader } = await getActiveWorkspaceContext();
  if (!workspace) notFound();

  const calls = await callsApi.list(workspace.id, "in_progress", { cookieHeader });

  return (
    <div className="space-y-6 p-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Live console</h1>
        <p className="text-muted-foreground">Calls currently in progress, streamed live via SSE.</p>
      </div>
      <LiveCallConsole workspaceId={workspace.id} initialCalls={calls} />
    </div>
  );
}
