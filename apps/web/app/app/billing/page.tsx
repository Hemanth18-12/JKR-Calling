import { billingApi } from "@jkr/sdk";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@jkr/ui";
import { notFound } from "next/navigation";

import { UsageSummaryView } from "@/components/usage-summary";
import { getActiveWorkspaceContext } from "@/lib/session";

export default async function BillingPage() {
  const { workspace, cookieHeader } = await getActiveWorkspaceContext();
  if (!workspace) notFound();

  const usage = await billingApi.usage(workspace.id, { cookieHeader });

  return (
    <div className="space-y-6 p-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Billing</h1>
        <p className="text-muted-foreground">Every call this workspace has run is mock — nothing here has cost anything yet.</p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Plan</CardTitle>
          <CardDescription>No subscription/invoicing this pass — see docs/IMPLEMENTATION_CHECKLIST.md Phase 9.</CardDescription>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          Real usage tracking and per-campaign budget enforcement are live below; plan management and invoices are not built yet.
        </CardContent>
      </Card>
      <UsageSummaryView usage={usage} />
    </div>
  );
}
