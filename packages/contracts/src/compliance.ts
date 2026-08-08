/**
 * Mirrors services/api/app/modules/compliance/schemas.py.
 */
import { z } from "zod";

export const AuditLogEntryOut = z.object({
  id: z.string().uuid(),
  actor_name: z.string().nullable(),
  action: z.string(),
  resource_type: z.string(),
  resource_id: z.string().nullable(),
  ip_address: z.string().nullable(),
  created_at: z.string(),
});
export type AuditLogEntryOut = z.infer<typeof AuditLogEntryOut>;

export const ConsentPurposeCount = z.object({ purpose: z.string(), count: z.number() });
export type ConsentPurposeCount = z.infer<typeof ConsentPurposeCount>;

export const ComplianceOverview = z.object({
  calling_window_start: z.string(),
  calling_window_end: z.string(),
  timezone: z.string(),
  total_contacts: z.number(),
  suppressed_contacts: z.number(),
  consent_purpose_breakdown: z.array(ConsentPurposeCount),
});
export type ComplianceOverview = z.infer<typeof ComplianceOverview>;
