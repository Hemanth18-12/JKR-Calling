import { z } from "zod";

export const TestCallCreate = z.object({
  agent_id: z.string().uuid(),
  contact_name: z.string().nullable().optional(),
});
export type TestCallCreate = z.infer<typeof TestCallCreate>;

export const TestCallStarted = z.object({
  call_id: z.string().uuid(),
  status: z.string(),
  language: z.string(),
  greeting: z.string(),
  conversation_state: z.record(z.unknown()),
});
export type TestCallStarted = z.infer<typeof TestCallStarted>;

export const LiveTestCallCreate = z.object({
  agent_id: z.string().uuid(),
  to_number: z.string().min(6).max(20),
});
export type LiveTestCallCreate = z.infer<typeof LiveTestCallCreate>;

export const LiveTestCallStarted = z.object({
  call_id: z.string().uuid(),
  call_sid: z.string(),
  status: z.string(),
});
export type LiveTestCallStarted = z.infer<typeof LiveTestCallStarted>;

export const TurnInfo = z.object({ turn_ref: z.string(), text: z.string() });
export type TurnInfo = z.infer<typeof TurnInfo>;

export const UserTurnResponse = z.object({
  user_turn: TurnInfo,
  interruption_classification: z.string(),
  stop_latency_ms: z.number().nullable(),
  agent_turn: TurnInfo.nullable(),
  conversation_state: z.record(z.unknown()),
  call_status: z.string(),
});
export type UserTurnResponse = z.infer<typeof UserTurnResponse>;

export const EndCallResponse = z.object({
  call_id: z.string().uuid(),
  status: z.string(),
  outcome_category: z.string(),
  lead_score: z.string(),
});
export type EndCallResponse = z.infer<typeof EndCallResponse>;

export const CallListItem = z.object({
  call_id: z.string().uuid(),
  status: z.string(),
  direction: z.string(),
  contact_name: z.string().nullable(),
  outcome_category: z.string().nullable(),
  started_at: z.string().nullable(),
  duration_seconds: z.number().nullable(),
  is_mock: z.boolean(),
});
export type CallListItem = z.infer<typeof CallListItem>;

export const CALL_STATUS_VARIANT: Record<string, "success" | "warning" | "secondary" | "danger" | "default"> = {
  queued: "secondary",
  dialing: "warning",
  ringing: "warning",
  in_progress: "warning",
  completed: "success",
  failed: "danger",
  no_answer: "secondary",
  busy: "secondary",
  transferred: "default",
  abandoned: "danger",
};

export const CallTurnOut = z.object({
  turn_ref: z.string(),
  sequence_index: z.number(),
  speaker: z.string(),
  text: z.string(),
  language: z.string().nullable(),
  confidence: z.number().nullable(),
  is_interrupted: z.boolean(),
  started_at: z.string(),
});
export type CallTurnOut = z.infer<typeof CallTurnOut>;

export const CallDetail = z.object({
  call_id: z.string().uuid(),
  status: z.string(),
  direction: z.string(),
  language: z.string().nullable(),
  agent_id: z.string().uuid(),
  started_at: z.string().nullable(),
  ended_at: z.string().nullable(),
  duration_seconds: z.number().nullable(),
  conversation_state: z.record(z.unknown()),
  turns: z.array(CallTurnOut),
  interruptions: z.array(
    z.object({ classification: z.string(), stop_latency_ms: z.number().nullable(), occurred_at: z.string() })
  ),
  latency_metrics: z.array(
    z.object({ stage: z.string(), duration_ms: z.number(), is_simulated: z.boolean(), recorded_at: z.string() })
  ),
  outcome: z
    .object({
      category: z.string(),
      lead_score: z.string().nullable(),
      score_reasons: z.array(z.string()),
      objective_status: z.string().nullable(),
      notes: z.string().nullable(),
    })
    .nullable(),
});
export type CallDetail = z.infer<typeof CallDetail>;
