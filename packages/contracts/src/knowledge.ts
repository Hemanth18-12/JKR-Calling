import { z } from "zod";

export const CollectionOut = z.object({
  id: z.string().uuid(),
  name: z.string(),
  description: z.string().nullable(),
  document_count: z.number(),
});
export type CollectionOut = z.infer<typeof CollectionOut>;

export const DocumentCreate = z.object({
  source_type: z.enum(["manual_faq", "text", "website", "pdf", "docx", "csv"]),
  title: z.string().min(1).max(300),
  collection_id: z.string().uuid().nullable().optional(),
  language: z.string().nullable().optional(),
  scope: z.enum(["workspace", "agent"]).default("workspace"),
  agent_ids: z.array(z.string().uuid()).default([]),
  raw_text: z.string().nullable().optional(),
  source_url: z.string().nullable().optional(),
  file_base64: z.string().nullable().optional(),
});
export type DocumentCreate = z.infer<typeof DocumentCreate>;

export const DocumentAgentsUpdate = z.object({
  scope: z.enum(["workspace", "agent"]),
  agent_ids: z.array(z.string().uuid()).default([]),
});
export type DocumentAgentsUpdate = z.infer<typeof DocumentAgentsUpdate>;

export const DocumentOut = z.object({
  id: z.string().uuid(),
  collection_id: z.string().uuid().nullable(),
  source_type: z.string(),
  title: z.string(),
  source_url: z.string().nullable(),
  approval_state: z.string(),
  scope: z.string().default("workspace"),
  agent_ids: z.array(z.string().uuid()).default([]),
  language: z.string().nullable(),
  sensitivity: z.string(),
  chunk_count: z.number(),
  created_at: z.string(),
});
export type DocumentOut = z.infer<typeof DocumentOut>;

export const DocumentDetail = DocumentOut.extend({
  raw_text_preview: z.string().nullable(),
});
export type DocumentDetail = z.infer<typeof DocumentDetail>;

export const ChunkOut = z.object({
  id: z.string().uuid(),
  chunk_index: z.number(),
  text: z.string(),
  approval_state: z.string(),
  page: z.number().nullable(),
  section: z.string().nullable(),
});
export type ChunkOut = z.infer<typeof ChunkOut>;

export const SearchRequest = z.object({
  query: z.string().min(1),
  agent_id: z.string().uuid().nullable().optional(),
  top_k: z.number().default(5),
});
export type SearchRequest = z.infer<typeof SearchRequest>;

export const SearchResultItem = z.object({
  chunk_id: z.string().uuid(),
  document_id: z.string().uuid(),
  document_title: z.string(),
  text: z.string(),
  score: z.number(),
});
export type SearchResultItem = z.infer<typeof SearchResultItem>;

export const SearchResponse = z.object({
  results: z.array(SearchResultItem),
  above_threshold: z.boolean(),
});
export type SearchResponse = z.infer<typeof SearchResponse>;

export const GenerateKnowledgeRequest = z.object({
  business_type: z.string().default("general"),
  agent_category: z.string().default("general"),
  language: z.string().default("en"),
  agent_id: z.string().uuid().nullable().optional(),
  answers: z.record(z.any()).default({}),
});
export type GenerateKnowledgeRequest = z.infer<typeof GenerateKnowledgeRequest>;

export const GenerateKnowledgeResponse = z.object({
  title: z.string(),
  generated_text: z.string(),
  health_score: z.number(),
  missing_fields: z.array(z.string()),
  suggestions: z.array(z.string()),
});
export type GenerateKnowledgeResponse = z.infer<typeof GenerateKnowledgeResponse>;

export const HealthScoreRequest = z.object({
  document_id: z.string().uuid().nullable().optional(),
  text: z.string().nullable().optional(),
  category: z.string().nullable().optional(),
});
export type HealthScoreRequest = z.infer<typeof HealthScoreRequest>;

export const HealthScoreResponse = z.object({
  score: z.number(),
  missing_sections: z.array(z.string()),
  suggestions: z.array(z.string()),
});
export type HealthScoreResponse = z.infer<typeof HealthScoreResponse>;

export const TestAgentRequest = z.object({
  agent_id: z.string().uuid().nullable().optional(),
  query: z.string().min(1),
  language: z.string().default("en"),
});
export type TestAgentRequest = z.infer<typeof TestAgentRequest>;

export const TestAgentResponse = z.object({
  answer: z.string(),
  grounded: z.boolean(),
  matched_chunks: z.array(SearchResultItem),
  used_scope: z.string(),
  latency_ms: z.record(z.number()),
});
export type TestAgentResponse = z.infer<typeof TestAgentResponse>;

export const KnowledgeGapItem = z.object({
  id: z.string().uuid(),
  query: z.string(),
  count: z.number(),
  last_asked_at: z.string().nullable().optional(),
});
export type KnowledgeGapItem = z.infer<typeof KnowledgeGapItem>;

export const SOURCE_TYPE_OPTIONS = [
  { value: "manual_faq", label: "Manual FAQ" },
  { value: "text", label: "Plain text" },
  { value: "website", label: "Website URL" },
  { value: "pdf", label: "PDF upload" },
  { value: "docx", label: "Word document upload" },
  { value: "csv", label: "CSV upload" },
] as const;

export const APPROVAL_STATE_VARIANT: Record<string, "success" | "warning" | "secondary" | "danger"> = {
  draft: "secondary",
  processing: "warning",
  needs_review: "warning",
  approved: "success",
  rejected: "danger",
  archived: "secondary",
};
