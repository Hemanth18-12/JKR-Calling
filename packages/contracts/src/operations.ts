/**
 * Mirrors services/api/app/modules/operations/schemas.py.
 */
import { z } from "zod";

export const FollowUpTaskOut = z.object({
  id: z.string().uuid(),
  contact_id: z.string().uuid(),
  contact_name: z.string(),
  call_session_id: z.string().uuid().nullable(),
  channel: z.string(),
  status: z.string(),
  scheduled_for: z.string().nullable(),
  payload: z.record(z.unknown()),
  completed_at: z.string().nullable(),
  created_at: z.string(),
});
export type FollowUpTaskOut = z.infer<typeof FollowUpTaskOut>;

export const HumanHandoffOut = z.object({
  id: z.string().uuid(),
  call_session_id: z.string().uuid(),
  contact_name: z.string().nullable(),
  reason: z.string(),
  status: z.string(),
  packet: z.record(z.unknown()),
  assigned_to_user_id: z.string().uuid().nullable(),
  resolved_at: z.string().nullable(),
  created_at: z.string(),
});
export type HumanHandoffOut = z.infer<typeof HumanHandoffOut>;

export const AppointmentOut = z.object({
  id: z.string().uuid(),
  contact_id: z.string().uuid(),
  contact_name: z.string(),
  call_session_id: z.string().uuid().nullable(),
  scheduled_for: z.string(),
  duration_minutes: z.number(),
  status: z.string(),
  location: z.string().nullable(),
  notes: z.string().nullable(),
  created_at: z.string(),
});
export type AppointmentOut = z.infer<typeof AppointmentOut>;

export const FOLLOW_UP_STATUS_VARIANT: Record<string, "success" | "warning" | "secondary" | "danger"> = {
  pending: "warning",
  scheduled: "warning",
  sent: "success",
  completed: "success",
  cancelled: "secondary",
};

export const HANDOFF_STATUS_VARIANT: Record<string, "success" | "warning" | "secondary" | "danger"> = {
  pending: "danger",
  accepted: "warning",
  resolved: "success",
  abandoned: "secondary",
};

export const APPOINTMENT_STATUS_VARIANT: Record<string, "success" | "warning" | "secondary" | "danger"> = {
  scheduled: "warning",
  confirmed: "success",
  rescheduled: "warning",
  cancelled: "danger",
  completed: "success",
  no_show: "danger",
};
