/**
 * Mirrors services/api/app/modules/billing/schemas.py.
 */
import { z } from "zod";

export const UsageByType = z.object({
  event_type: z.string(),
  unit: z.string(),
  total_quantity: z.number(),
  event_count: z.number(),
});
export type UsageByType = z.infer<typeof UsageByType>;

export const CampaignBudget = z.object({
  campaign_id: z.string(),
  campaign_name: z.string(),
  daily_budget_paise: z.number(),
  spent_today_paise: z.number(),
});
export type CampaignBudget = z.infer<typeof CampaignBudget>;

export const UsageSummary = z.object({
  usage_by_type: z.array(UsageByType),
  total_calls: z.number(),
  total_call_seconds: z.number(),
  campaign_budgets: z.array(CampaignBudget),
});
export type UsageSummary = z.infer<typeof UsageSummary>;
