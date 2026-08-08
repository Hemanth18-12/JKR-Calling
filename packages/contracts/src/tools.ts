/**
 * Mirrors services/api/app/modules/tools/schemas.py.
 */
import { z } from "zod";

export const ToolDefinitionOut = z.object({
  id: z.string().uuid(),
  name: z.string(),
  description: z.string(),
  required_permission: z.string(),
  timeout_seconds: z.number(),
  confirmation_required: z.boolean(),
  is_enabled: z.boolean(),
  has_real_side_effect: z.boolean(),
});
export type ToolDefinitionOut = z.infer<typeof ToolDefinitionOut>;

export const AgentToolOut = z.object({
  tool_definition_id: z.string().uuid(),
  name: z.string(),
  description: z.string(),
  enabled: z.boolean(),
});
export type AgentToolOut = z.infer<typeof AgentToolOut>;

export const ToolExecutionOut = z.object({
  id: z.string().uuid(),
  tool_definition_id: z.string().uuid(),
  tool_name: z.string(),
  status: z.string(),
  input: z.record(z.unknown()),
  output: z.record(z.unknown()).nullable(),
  error: z.string().nullable(),
  started_at: z.string(),
  completed_at: z.string().nullable(),
});
export type ToolExecutionOut = z.infer<typeof ToolExecutionOut>;

export const TOOL_NAME_LABELS: Record<string, string> = {
  check_calendar_slots: "Check calendar slots",
  book_appointment: "Book appointment",
  reschedule_appointment: "Reschedule appointment",
  cancel_appointment: "Cancel appointment",
  create_crm_lead: "Create CRM lead",
  update_crm_stage: "Update CRM stage",
  create_human_callback: "Human callback",
  send_whatsapp: "Send WhatsApp",
  send_sms: "Send SMS",
  send_email: "Send email",
};
