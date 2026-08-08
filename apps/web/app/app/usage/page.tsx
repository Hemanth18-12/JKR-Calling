import { billingApi } from "@jkr/sdk";
import { notFound } from "next/navigation";

import { UsageSummaryView } from "@/components/usage-summary";
import { getActiveWorkspaceContext } from "@/lib/session";

export default async function UsagePage() {
  const { workspace, cookieHeader } = await getActiveWorkspaceContext();
  if (!workspace) notFound();

  const usage = await billingApi.usage(workspace.id, { cookieHeader });

  return (
    <div className="space-y-6 p-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Usage</h1>
        <p className="text-muted-foreground">Real metered usage from actual calls — what a real provider bill would be based on.</p>
      </div>
      <UsageSummaryView usage={usage} />
    </div>
  );
}
