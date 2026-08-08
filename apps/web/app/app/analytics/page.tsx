import { analyticsApi } from "@jkr/sdk";
import { notFound } from "next/navigation";

import { AnalyticsDashboard } from "@/components/analytics-dashboard";
import { getActiveWorkspaceContext } from "@/lib/session";

export default async function AnalyticsPage() {
  const { workspace, cookieHeader } = await getActiveWorkspaceContext();
  if (!workspace) notFound();

  const [overview, calls, quality, providers] = await Promise.all([
    analyticsApi.overview(workspace.id, { cookieHeader }),
    analyticsApi.calls(workspace.id, { cookieHeader }),
    analyticsApi.conversationQuality(workspace.id, { cookieHeader }),
    analyticsApi.providers(workspace.id, { cookieHeader }),
  ]);

  return (
    <div className="space-y-6 p-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Analytics</h1>
        <p className="text-muted-foreground">Computed directly from calls, outcomes, and quality evaluations — never a separate, driftable copy.</p>
      </div>
      <AnalyticsDashboard overview={overview} calls={calls} quality={quality} providers={providers} />
    </div>
  );
}
