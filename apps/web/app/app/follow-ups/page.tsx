import { operationsApi } from "@jkr/sdk";
import { notFound } from "next/navigation";

import { FollowUpsList } from "@/components/follow-ups-list";
import { getActiveWorkspaceContext } from "@/lib/session";

export default async function FollowUpsPage() {
  const { workspace, cookieHeader } = await getActiveWorkspaceContext();
  if (!workspace) notFound();

  const tasks = await operationsApi.listFollowUps(workspace.id, undefined, { cookieHeader });

  return (
    <div className="space-y-6 p-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Follow-ups</h1>
        <p className="text-muted-foreground">What post-call intelligence planned (and, where possible, already actioned) after each call.</p>
      </div>
      <FollowUpsList workspaceId={workspace.id} tasks={tasks} />
    </div>
  );
}
