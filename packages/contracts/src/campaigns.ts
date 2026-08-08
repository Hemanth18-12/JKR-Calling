/**
 * Mirrors services/api/app/modules/campaigns/schemas.py.
 */
import { z } from "zod";

export const CampaignCreate = z.object({
  name: z.string().min(1).max(150),
  objective: z.enum(["book_appointment", "qualify_lead", "collect_feedback", "renewal_reminder", "custom"]),
  agent_id: z.string().uuid(),
  audience_segment_id: z.string().uuid().nullable().optional(),
  required_fields: z.array(z.string()).default([]),
  optional_fields: z.array(z.string()).default([]),
  success_conditions: z.array(z.string()).default([]),
  stop_conditions: z.array(z.string()).default([]),
  max_attempts: z.number().min(1).max(10).default(3),
  daily_budget_paise: z.number().min(0).nullable().optional(),
});
export type CampaignCreate = z.infer<typeof CampaignCreate>;

export const CampaignOut = z.object({
  id: z.string().uuid(),
  name: z.string(),
  objective: z.string(),
  agent_id: z.string().uuid(),
  agent_version_id: z.string().uuid(),
  audience_segment_id: z.string().uuid().nullable(),
  status: z.string(),
  mode: z.string(),
  max_attempts: z.number(),
  daily_budget_paise: z.number().nullable(),
  legal_reviewed_at: z.string().nullable(),
  created_at: z.string(),
});
export type CampaignOut = z.infer<typeof CampaignOut>;

export const CampaignScheduleOut = z.object({
  calling_window_start: z.string(),
  calling_window_end: z.string(),
  days_of_week: z.array(z.number()),
  timezone: z.string(),
});
export type CampaignScheduleOut = z.infer<typeof CampaignScheduleOut>;

export const CampaignContactSummary = z.object({ status: z.string(), count: z.number() });
export type CampaignContactSummary = z.infer<typeof CampaignContactSummary>;

export const CampaignDetail = CampaignOut.extend({
  schedule: CampaignScheduleOut.nullable(),
  contact_counts: z.array(CampaignContactSummary),
});
export type CampaignDetail = z.infer<typeof CampaignDetail>;

export const CampaignContactOut = z.object({
  id: z.string().uuid(),
  contact_id: z.string().uuid(),
  contact_name: z.string(),
  phone_masked: z.string(),
  status: z.string(),
  attempt_count: z.number(),
  last_attempt_at: z.string().nullable(),
  next_attempt_at: z.string().nullable(),
});
export type CampaignContactOut = z.infer<typeof CampaignContactOut>;

export const AddContactsRequest = z.object({
  contact_ids: z.array(z.string().uuid()).default([]),
  segment_id: z.string().uuid().nullable().optional(),
});
export type AddContactsRequest = z.infer<typeof AddContactsRequest>;

export const GateCheckResult = z.object({ check: z.string(), passed: z.boolean(), detail: z.string().nullable() });
export type GateCheckResult = z.infer<typeof GateCheckResult>;

export const DryRunContactResult = z.object({
  campaign_contact_id: z.string().uuid(),
  contact_id: z.string().uuid(),
  contact_name: z.string(),
  would_dispatch: z.boolean(),
  failed_check: z.string().nullable(),
  checks: z.array(GateCheckResult),
});
export type DryRunContactResult = z.infer<typeof DryRunContactResult>;

export const DryRunResponse = z.object({
  campaign_id: z.string().uuid(),
  evaluated: z.number(),
  would_dispatch: z.number(),
  blocked: z.number(),
  results: z.array(DryRunContactResult),
});
export type DryRunResponse = z.infer<typeof DryRunResponse>;

export const CampaignAttemptOut = z.object({
  id: z.string().uuid(),
  attempt_number: z.number(),
  call_session_id: z.string().uuid().nullable(),
  dispatched: z.boolean(),
  outcome: z.string().nullable(),
  failure_reason: z.string().nullable(),
  gate_result: z.record(z.unknown()),
  created_at: z.string(),
});
export type CampaignAttemptOut = z.infer<typeof CampaignAttemptOut>;

export const CAMPAIGN_OBJECTIVE_OPTIONS = [
  { value: "qualify_lead", label: "Qualify lead" },
  { value: "book_appointment", label: "Book appointment" },
  { value: "collect_feedback", label: "Collect feedback" },
  { value: "renewal_reminder", label: "Renewal reminder" },
  { value: "custom", label: "Custom" },
] as const;

export const CAMPAIGN_STATUS_VARIANT: Record<string, "success" | "warning" | "secondary" | "danger" | "default"> = {
  draft: "secondary",
  validating: "warning",
  scheduled: "warning",
  active: "success",
  paused: "warning",
  completed: "default",
  cancelled: "secondary",
  failed: "danger",
};

export const CAMPAIGN_CONTACT_STATUS_VARIANT: Record<string, "success" | "warning" | "secondary" | "danger" | "default"> = {
  pending: "secondary",
  reserved: "warning",
  dialing: "warning",
  ringing: "warning",
  in_progress: "warning",
  completed: "success",
  no_answer: "warning",
  busy: "warning",
  failed: "danger",
  retry_scheduled: "warning",
  human_review: "warning",
  suppressed: "danger",
};
