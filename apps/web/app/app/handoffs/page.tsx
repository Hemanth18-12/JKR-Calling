import { operationsApi } from "@jkr/sdk";
import { notFound } from "next/navigation";

import { HandoffsList } from "@/components/handoffs-list";
import { getActiveWorkspaceContext } from "@/lib/session";

export default async function HandoffsPage() {
  const { workspace, cookieHeader } = await getActiveWorkspaceContext();
  if (!workspace) notFound();

  const handoffs = await operationsApi.listHandoffs(workspace.id, undefined, { cookieHeader });

  return (
    <div className="space-y-6 p-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Handoffs</h1>
        <p className="text-muted-foreground">Calls an agent escalated to a human team member.</p>
      </div>
      <HandoffsList workspaceId={workspace.id} handoffs={handoffs} />
    </div>
  );
}
