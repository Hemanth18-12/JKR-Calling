import { billingApi } from "@jkr/sdk";
import { EmptyState } from "@jkr/ui";
import { Building2 } from "lucide-react";

import { UsageSummaryView } from "@/components/usage-summary";
import { getActiveWorkspaceContext } from "@/lib/session";

export default async function UsagePage() {
  const { workspace, cookieHeader } = await getActiveWorkspaceContext();
  if (!workspace) {
    return (
      <div className="p-8">
        <EmptyState icon={Building2} title="No workspace yet" description="Select or create a workspace to view usage." />
      </div>
    );
  }

  let usage;
  try {
    usage = await billingApi.usage(workspace.id, { cookieHeader });
  } catch (err) {
    console.error("Failed to fetch billing usage:", err);
    usage = {
      usage_by_type: [],
      total_calls: 0,
      total_call_seconds: 0,
      campaign_budgets: [],
    };
  }

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
