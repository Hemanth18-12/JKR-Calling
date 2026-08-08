/**
 * Mirrors services/api/app/modules/contacts/schemas.py.
 */
import { z } from "zod";

export const ContactCreate = z.object({
  full_name: z.string().min(1).max(200),
  phone: z.string().min(6).max(32),
  email: z.string().nullable().optional(),
  preferred_language: z.string().nullable().optional(),
  location: z.string().nullable().optional(),
  lead_source: z.string().nullable().optional(),
});
export type ContactCreate = z.infer<typeof ContactCreate>;

export const ContactOut = z.object({
  id: z.string().uuid(),
  full_name: z.string(),
  phone_masked: z.string(),
  email: z.string().nullable(),
  preferred_language: z.string().nullable(),
  location: z.string().nullable(),
  lead_source: z.string().nullable(),
  consent_status: z.string(),
  is_suppressed: z.boolean(),
  conversion_status: z.string().nullable(),
  last_call_at: z.string().nullable(),
  created_at: z.string(),
});
export type ContactOut = z.infer<typeof ContactOut>;

export const ContactDetail = ContactOut.extend({ phone_e164: z.string().nullable() });
export type ContactDetail = z.infer<typeof ContactDetail>;

export const ConsentEventCreate = z.object({
  purpose: z.enum(["marketing", "transactional", "service", "appointment_reminder"]),
  source: z.enum(["signed_form", "verbal_recorded", "checkbox", "whatsapp_opt_in", "api"]),
  campaign_category: z.string().nullable().optional(),
  evidence_url: z.string().nullable().optional(),
  expires_at: z.string().nullable().optional(),
});
export type ConsentEventCreate = z.infer<typeof ConsentEventCreate>;

export const ConsentEventOut = z.object({
  id: z.string().uuid(),
  contact_id: z.string().uuid(),
  purpose: z.string(),
  source: z.string(),
  campaign_category: z.string().nullable(),
  granted_at: z.string(),
  expires_at: z.string().nullable(),
  revoked_at: z.string().nullable(),
});
export type ConsentEventOut = z.infer<typeof ConsentEventOut>;

export const SuppressionCreate = z.object({
  phone: z.string().min(6).max(32),
  reason: z.enum([
    "customer_opt_out", "wrong_number", "legal_suppression", "workspace_block", "complaint", "repeated_failure", "manual_block",
  ]),
  note: z.string().nullable().optional(),
});
export type SuppressionCreate = z.infer<typeof SuppressionCreate>;

export const SuppressionOut = z.object({
  id: z.string().uuid(),
  contact_id: z.string().uuid().nullable(),
  phone_masked: z.string(),
  reason: z.string(),
  note: z.string().nullable(),
  created_at: z.string(),
});
export type SuppressionOut = z.infer<typeof SuppressionOut>;

export const SegmentCreate = z.object({
  name: z.string().min(1).max(150),
  description: z.string().nullable().optional(),
  contact_ids: z.array(z.string().uuid()).default([]),
});
export type SegmentCreate = z.infer<typeof SegmentCreate>;

export const SegmentOut = z.object({
  id: z.string().uuid(),
  name: z.string(),
  description: z.string().nullable(),
  member_count: z.number(),
});
export type SegmentOut = z.infer<typeof SegmentOut>;

export const CONSENT_PURPOSE_OPTIONS = [
  { value: "marketing", label: "Marketing" },
  { value: "transactional", label: "Transactional" },
  { value: "service", label: "Service" },
  { value: "appointment_reminder", label: "Appointment reminder" },
] as const;

export const CONSENT_SOURCE_OPTIONS = [
  { value: "verbal_recorded", label: "Verbal (recorded)" },
  { value: "signed_form", label: "Signed form" },
  { value: "checkbox", label: "Checkbox opt-in" },
  { value: "whatsapp_opt_in", label: "WhatsApp opt-in" },
  { value: "api", label: "API" },
] as const;

export const SUPPRESSION_REASON_OPTIONS = [
  { value: "customer_opt_out", label: "Customer opted out" },
  { value: "wrong_number", label: "Wrong number" },
  { value: "complaint", label: "Complaint" },
  { value: "repeated_failure", label: "Repeated failure" },
  { value: "legal_suppression", label: "Legal suppression" },
  { value: "workspace_block", label: "Workspace block" },
  { value: "manual_block", label: "Manual block" },
] as const;
