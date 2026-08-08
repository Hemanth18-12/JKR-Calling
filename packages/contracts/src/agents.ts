/**
 * Mirrors services/api/app/modules/agents/schemas.py.
 */
import { z } from "zod";

export const AgentCreate = z.object({
  name: z.string().min(1).max(150),
  business_identity: z.string().min(1).max(200),
  description: z.string().nullable().optional(),
  primary_language: z.string().default("te-en-IN"),
  persona_template: z.string().default("warm_receptionist"),
});
export type AgentCreate = z.infer<typeof AgentCreate>;

export const AgentUpdate = z.object({
  name: z.string().min(1).max(150).optional(),
  business_identity: z.string().min(1).max(200).optional(),
  description: z.string().nullable().optional(),
  primary_language: z.string().optional(),
});
export type AgentUpdate = z.infer<typeof AgentUpdate>;

export const AgentOut = z.object({
  id: z.string().uuid(),
  name: z.string(),
  business_identity: z.string(),
  description: z.string().nullable(),
  status: z.string(),
  primary_language: z.string(),
  published_version_id: z.string().uuid().nullable(),
  active_phone_number_id: z.string().uuid().nullable(),
  persona_template: z.string().nullable(),
  created_at: z.string(),
});
export type AgentOut = z.infer<typeof AgentOut>;

export const AgentVersionOut = z.object({
  id: z.string().uuid(),
  agent_id: z.string().uuid(),
  version_number: z.number(),
  status: z.string(),
  primary_objective: z.string(),
  ai_disclosure_text: z.string(),
  greeting_text: z.string(),
  closing_text: z.string(),
  personality: z.string(),
  formality: z.string(),
  energy: z.string(),
  response_length: z.string(),
  use_honorifics: z.boolean(),
  supported_languages: z.array(z.string()),
  code_switching_behavior: z.string(),
  restricted_phrases: z.array(z.string()),
  escalation_policy: z.record(z.unknown()),
  quality_score: z.number().nullable(),
  published_at: z.string().nullable(),
  created_at: z.string(),
});
export type AgentVersionOut = z.infer<typeof AgentVersionOut>;

export const AgentDetail = AgentOut.extend({ versions: z.array(AgentVersionOut) });
export type AgentDetail = z.infer<typeof AgentDetail>;

export const AgentVersionUpdate = z.object({
  primary_objective: z.string().optional(),
  ai_disclosure_text: z.string().optional(),
  greeting_text: z.string().optional(),
  closing_text: z.string().optional(),
  personality: z.string().optional(),
  formality: z.string().optional(),
  energy: z.string().optional(),
  response_length: z.string().optional(),
  use_honorifics: z.boolean().optional(),
  supported_languages: z.array(z.string()).optional(),
  code_switching_behavior: z.string().optional(),
  restricted_phrases: z.array(z.string()).optional(),
  escalation_policy: z.record(z.unknown()).optional(),
});
export type AgentVersionUpdate = z.infer<typeof AgentVersionUpdate>;

export const VoicePersonaOut = z.object({
  id: z.string().uuid(),
  provider: z.string(),
  voice_id: z.string(),
  gender_presentation: z.string(),
  language: z.string(),
  speaking_speed: z.number(),
  stability: z.number(),
  expressiveness: z.number(),
  fallback_voice_id: z.string().nullable(),
  sample_audio_url: z.string().nullable(),
});
export type VoicePersonaOut = z.infer<typeof VoicePersonaOut>;

export const VoicePersonaUpdate = z.object({
  provider: z.string().optional(),
  voice_id: z.string().optional(),
  gender_presentation: z.string().optional(),
  language: z.string().optional(),
  speaking_speed: z.number().min(0.5).max(2.0).optional(),
  stability: z.number().min(0).max(1).optional(),
  expressiveness: z.number().min(0).max(1).optional(),
  fallback_voice_id: z.string().nullable().optional(),
});
export type VoicePersonaUpdate = z.infer<typeof VoicePersonaUpdate>;

export const ConversationPolicyOut = z.object({
  id: z.string().uuid(),
  interruption_enabled: z.boolean(),
  min_interruption_ms: z.number(),
  accidental_interruption_phrases: z.array(z.string()),
  silence_timeout_ms: z.number(),
  max_monologue_ms: z.number(),
  max_response_sentences: z.number(),
  confirmation_behavior: z.string(),
  clarification_behavior: z.string(),
  background_noise_tolerance: z.string(),
  human_transfer_enabled: z.boolean(),
  call_later_enabled: z.boolean(),
  wrong_number_behavior: z.string(),
  do_not_call_behavior: z.string(),
});
export type ConversationPolicyOut = z.infer<typeof ConversationPolicyOut>;

export const ConversationPolicyUpdate = z.object({
  interruption_enabled: z.boolean().optional(),
  min_interruption_ms: z.number().min(0).max(5000).optional(),
  accidental_interruption_phrases: z.array(z.string()).optional(),
  silence_timeout_ms: z.number().min(1000).max(60000).optional(),
  max_monologue_ms: z.number().min(1000).max(60000).optional(),
  max_response_sentences: z.number().min(1).max(10).optional(),
  confirmation_behavior: z.string().optional(),
  clarification_behavior: z.string().optional(),
  background_noise_tolerance: z.string().optional(),
  human_transfer_enabled: z.boolean().optional(),
  call_later_enabled: z.boolean().optional(),
  wrong_number_behavior: z.string().optional(),
  do_not_call_behavior: z.string().optional(),
});
export type ConversationPolicyUpdate = z.infer<typeof ConversationPolicyUpdate>;

export const PronunciationEntryOut = z.object({
  id: z.string().uuid(),
  term: z.string(),
  pronunciation: z.string(),
  language: z.string(),
});
export type PronunciationEntryOut = z.infer<typeof PronunciationEntryOut>;

export const PronunciationEntryCreate = z.object({
  term: z.string().min(1).max(200),
  pronunciation: z.string().min(1).max(200),
  language: z.string(),
});
export type PronunciationEntryCreate = z.infer<typeof PronunciationEntryCreate>;

export const AgentVersionDetail = AgentVersionOut.extend({
  voice_persona: VoicePersonaOut.nullable(),
  conversation_policy: ConversationPolicyOut.nullable(),
  pronunciation_entries: z.array(PronunciationEntryOut),
});
export type AgentVersionDetail = z.infer<typeof AgentVersionDetail>;

export const PersonaTemplateOut = z.object({ key: z.string(), label: z.string() });
export type PersonaTemplateOut = z.infer<typeof PersonaTemplateOut>;

export const LANGUAGE_OPTIONS = [
  { value: "te-IN", label: "Telugu" },
  { value: "hi-IN", label: "Hindi" },
  { value: "en-IN", label: "English (India)" },
  { value: "te-en-IN", label: "Telugu-English" },
  { value: "hi-en-IN", label: "Hindi-English" },
] as const;
