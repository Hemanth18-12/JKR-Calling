import { analyticsApi } from "@jkr/sdk";
import { notFound } from "next/navigation";

import { AnalyticsDashboard } from "@/components/analytics-dashboard";
import { getActiveWorkspaceContext } from "@/lib/session";

export default async function AnalyticsPage() {
  const { workspace, cookieHeader } = await getActiveWorkspaceContext();
  if (!workspace) notFound();

  const [overview, calls, quality, providers] = await Promise.all([
    analyticsApi.overview(workspace.id, { cookieHeader }).catch(() => ({
      total_calls: 0,
      connected_calls: 0,
      connect_rate: 0,
      appointments_booked: 0,
      contacts_reached: 0,
      active_campaigns: 0,
      pending_handoffs: 0,
      revenue_paise: 0,
      revenue_event_count: 0,
    })),
    analyticsApi.calls(workspace.id, { cookieHeader }).catch(() => ({
      status_breakdown: [],
      outcome_breakdown: [],
      lead_score_breakdown: [],
      avg_duration_seconds: null,
      mock_call_count: 0,
      real_call_count: 0,
      funnel: [],
    })),
    analyticsApi.conversationQuality(workspace.id, { cookieHeader }).catch(() => ({
      calls_evaluated: 0,
      avg_overall_score: null,
      disclosure_present_rate: null,
      avg_interruption_quality_score: null,
      avg_knowledge_grounding_score: null,
      needs_human_review_rate: null,
      long_monologue_rate: null,
    })),
    analyticsApi.providers(workspace.id, { cookieHeader }).catch(() => ({
      latency_by_stage: [],
      account_health: [],
    })),
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
