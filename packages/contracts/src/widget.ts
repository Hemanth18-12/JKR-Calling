import { z } from "zod";

export const WidgetConfigResponse = z.object({
  agent_id: z.string(),
  name: z.string(),
  business_identity: z.string(),
  primary_language: z.string(),
  supported_languages: z.array(z.string()),
  greeting_text: z.string(),
  primary_objective: z.string(),
  theme_color: z.string(),
  position: z.string(),
  launcher_text: z.string(),
  allow_voice: z.boolean(),
});
export type WidgetConfigResponse = z.infer<typeof WidgetConfigResponse>;

export const StartWidgetSessionRequest = z.object({
  agent_id: z.string().uuid(),
  visitor_name: z.string().optional(),
  visitor_phone: z.string().optional(),
  language: z.string().optional(),
});
export type StartWidgetSessionRequest = z.infer<typeof StartWidgetSessionRequest>;

export const StartWidgetSessionResponse = z.object({
  session_id: z.string(),
  agent_name: z.string(),
  business_identity: z.string(),
  greeting: z.string(),
  language: z.string(),
  theme_color: z.string(),
});
export type StartWidgetSessionResponse = z.infer<typeof StartWidgetSessionResponse>;

export const WidgetMessageRequest = z.object({
  message: z.string(),
  language: z.string().optional(),
});
export type WidgetMessageRequest = z.infer<typeof WidgetMessageRequest>;

export const WidgetMessageResponse = z.object({
  reply_text: z.string(),
  audio_url: z.string().nullable().optional(),
  turn_ref: z.string(),
  session_status: z.string(),
  appointment_booked: z.boolean(),
  tools_executed: z.array(z.string()),
});
export type WidgetMessageResponse = z.infer<typeof WidgetMessageResponse>;
