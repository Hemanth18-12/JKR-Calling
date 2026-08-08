import type { ChunkOut, CollectionOut, DocumentCreate, DocumentDetail, DocumentOut, SearchRequest, SearchResponse } from "@jkr/contracts";

import { type ApiFetchOptions, apiFetch } from "./client";

function qs(workspaceId: string) {
  return `?${new URLSearchParams({ workspace_id: workspaceId }).toString()}`;
}

export const knowledgeApi = {
  listCollections: (workspaceId: string, opts?: ApiFetchOptions) =>
    apiFetch<CollectionOut[]>(`/knowledge/collections${qs(workspaceId)}`, { ...opts, method: "GET" }),
  createCollection: (workspaceId: string, data: { name: string; description?: string | null }, opts?: ApiFetchOptions) =>
    apiFetch<CollectionOut>(`/knowledge/collections${qs(workspaceId)}`, { ...opts, method: "POST", body: data }),
  listDocuments: (workspaceId: string, opts?: ApiFetchOptions) =>
    apiFetch<DocumentOut[]>(`/knowledge/documents${qs(workspaceId)}`, { ...opts, method: "GET" }),
  createDocument: (workspaceId: string, data: DocumentCreate, opts?: ApiFetchOptions) =>
    apiFetch<DocumentOut>(`/knowledge/documents${qs(workspaceId)}`, { ...opts, method: "POST", body: data }),
  getDocument: (workspaceId: string, documentId: string, opts?: ApiFetchOptions) =>
    apiFetch<DocumentDetail>(`/knowledge/documents/${documentId}${qs(workspaceId)}`, { ...opts, method: "GET" }),
  getChunks: (workspaceId: string, documentId: string, opts?: ApiFetchOptions) =>
    apiFetch<ChunkOut[]>(`/knowledge/documents/${documentId}/chunks${qs(workspaceId)}`, { ...opts, method: "GET" }),
  processDocument: (workspaceId: string, documentId: string, opts?: ApiFetchOptions) =>
    apiFetch<DocumentOut>(`/knowledge/documents/${documentId}/process${qs(workspaceId)}`, { ...opts, method: "POST" }),
  approveDocument: (workspaceId: string, documentId: string, notes: string | null, opts?: ApiFetchOptions) =>
    apiFetch<DocumentOut>(`/knowledge/documents/${documentId}/approve${qs(workspaceId)}`, { ...opts, method: "POST", body: { notes } }),
  rejectDocument: (workspaceId: string, documentId: string, notes: string | null, opts?: ApiFetchOptions) =>
    apiFetch<DocumentOut>(`/knowledge/documents/${documentId}/reject${qs(workspaceId)}`, { ...opts, method: "POST", body: { notes } }),
  search: (workspaceId: string, data: SearchRequest, opts?: ApiFetchOptions) =>
    apiFetch<SearchResponse>(`/knowledge/search${qs(workspaceId)}`, { ...opts, method: "POST", body: data }),
};
