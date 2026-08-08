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
  raw_text: z.string().nullable().optional(),
  source_url: z.string().nullable().optional(),
  file_base64: z.string().nullable().optional(),
});
export type DocumentCreate = z.infer<typeof DocumentCreate>;

export const DocumentOut = z.object({
  id: z.string().uuid(),
  collection_id: z.string().uuid().nullable(),
  source_type: z.string(),
  title: z.string(),
  source_url: z.string().nullable(),
  approval_state: z.string(),
  language: z.string().nullable(),
  sensitivity: z.string(),
  chunk_count: z.number(),
  created_at: z.string(),
});
export type DocumentOut = z.infer<typeof DocumentOut>;

export const DocumentDetail = DocumentOut.extend({ raw_text_preview: z.string().nullable() });
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

export const SearchRequest = z.object({ query: z.string().min(1), top_k: z.number().default(5) });
export type SearchRequest = z.infer<typeof SearchRequest>;

export const SearchResultItem = z.object({
  chunk_id: z.string().uuid(),
  document_id: z.string().uuid(),
  document_title: z.string(),
  text: z.string(),
  score: z.number(),
});
export type SearchResultItem = z.infer<typeof SearchResultItem>;

export const SearchResponse = z.object({ results: z.array(SearchResultItem), above_threshold: z.boolean() });
export type SearchResponse = z.infer<typeof SearchResponse>;

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
