/**
 * Mirrors services/api/app/modules/analytics/schemas.py.
 */
import { z } from "zod";

export const CountBucket = z.object({ key: z.string(), count: z.number() });
export type CountBucket = z.infer<typeof CountBucket>;

export const BusinessOverview = z.object({
  total_calls: z.number(),
  connected_calls: z.number(),
  connect_rate: z.number(),
  appointments_booked: z.number(),
  contacts_reached: z.number(),
  active_campaigns: z.number(),
  pending_handoffs: z.number(),
  revenue_paise: z.number(),
  revenue_event_count: z.number(),
});
export type BusinessOverview = z.infer<typeof BusinessOverview>;

export const FunnelStage = z.object({ stage: z.string(), count: z.number() });
export type FunnelStage = z.infer<typeof FunnelStage>;

export const CallAnalytics = z.object({
  status_breakdown: z.array(CountBucket),
  outcome_breakdown: z.array(CountBucket),
  lead_score_breakdown: z.array(CountBucket),
  avg_duration_seconds: z.number().nullable(),
  mock_call_count: z.number(),
  real_call_count: z.number(),
  funnel: z.array(FunnelStage),
});
export type CallAnalytics = z.infer<typeof CallAnalytics>;

export const ConversationQuality = z.object({
  calls_evaluated: z.number(),
  avg_overall_score: z.number().nullable(),
  disclosure_present_rate: z.number().nullable(),
  avg_interruption_quality_score: z.number().nullable(),
  avg_knowledge_grounding_score: z.number().nullable(),
  needs_human_review_rate: z.number().nullable(),
  long_monologue_rate: z.number().nullable(),
});
export type ConversationQuality = z.infer<typeof ConversationQuality>;

export const ProviderLatencyStage = z.object({ stage: z.string(), avg_duration_ms: z.number(), sample_count: z.number() });
export type ProviderLatencyStage = z.infer<typeof ProviderLatencyStage>;

export const ProviderAccountHealth = z.object({
  kind: z.string(),
  name: z.string(),
  display_name: z.string(),
  status: z.string(),
  latency_p50_ms: z.number().nullable(),
});
export type ProviderAccountHealth = z.infer<typeof ProviderAccountHealth>;

export const ProviderAnalytics = z.object({
  latency_by_stage: z.array(ProviderLatencyStage),
  account_health: z.array(ProviderAccountHealth),
});
export type ProviderAnalytics = z.infer<typeof ProviderAnalytics>;
