import type {
  ChunkOut,
  CollectionOut,
  DocumentAgentsUpdate,
  DocumentCreate,
  DocumentDetail,
  DocumentOut,
  GenerateKnowledgeRequest,
  GenerateKnowledgeResponse,
  HealthScoreRequest,
  HealthScoreResponse,
  KnowledgeGapItem,
  SearchRequest,
  SearchResponse,
  TestAgentRequest,
  TestAgentResponse,
} from "@jkr/contracts";

import { type ApiFetchOptions, apiFetch } from "./client";

function qs(workspaceId: string, extra?: Record<string, string | undefined>) {
  const params = new URLSearchParams({ workspace_id: workspaceId });
  if (extra) {
    for (const [k, v] of Object.entries(extra)) {
      if (v !== undefined) {
        params.append(k, v);
      }
    }
  }
  return `?${params.toString()}`;
}

export const knowledgeApi = {
  listCollections: (workspaceId: string, opts?: ApiFetchOptions) =>
    apiFetch<CollectionOut[]>(`/knowledge/collections${qs(workspaceId)}`, { ...opts, method: "GET" }),
  createCollection: (workspaceId: string, data: { name: string; description?: string | null }, opts?: ApiFetchOptions) =>
    apiFetch<CollectionOut>(`/knowledge/collections${qs(workspaceId)}`, { ...opts, method: "POST", body: data }),
  listDocuments: (workspaceId: string, agentIdOrOpts?: string | ApiFetchOptions, opts?: ApiFetchOptions) => {
    let agentId: string | undefined;
    let actualOpts = opts;
    if (typeof agentIdOrOpts === "string") {
      agentId = agentIdOrOpts;
    } else if (agentIdOrOpts && typeof agentIdOrOpts === "object") {
      actualOpts = agentIdOrOpts;
    }
    return apiFetch<DocumentOut[]>(`/knowledge/documents${qs(workspaceId, { agent_id: agentId })}`, { ...actualOpts, method: "GET" });
  },
  createDocument: (workspaceId: string, data: DocumentCreate, opts?: ApiFetchOptions) =>
    apiFetch<DocumentOut>(`/knowledge/documents${qs(workspaceId)}`, { ...opts, method: "POST", body: data }),
  getDocument: (workspaceId: string, documentId: string, opts?: ApiFetchOptions) =>
    apiFetch<DocumentDetail>(`/knowledge/documents/${documentId}${qs(workspaceId)}`, { ...opts, method: "GET" }),
  updateDocumentAgents: (workspaceId: string, documentId: string, data: DocumentAgentsUpdate, opts?: ApiFetchOptions) =>
    apiFetch<DocumentDetail>(`/knowledge/documents/${documentId}/agents${qs(workspaceId)}`, { ...opts, method: "PUT", body: data }),
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
  generateFromAnswers: (workspaceId: string, data: GenerateKnowledgeRequest, opts?: ApiFetchOptions) =>
    apiFetch<GenerateKnowledgeResponse>(`/knowledge/generate-from-answers${qs(workspaceId)}`, { ...opts, method: "POST", body: data }),
  getHealthScore: (workspaceId: string, data: HealthScoreRequest, opts?: ApiFetchOptions) =>
    apiFetch<HealthScoreResponse>(`/knowledge/health-score${qs(workspaceId)}`, { ...opts, method: "POST", body: data }),
  testAgent: (workspaceId: string, data: TestAgentRequest, opts?: ApiFetchOptions) =>
    apiFetch<TestAgentResponse>(`/knowledge/test-agent${qs(workspaceId)}`, { ...opts, method: "POST", body: data }),
  listGaps: (workspaceId: string, agentId?: string, opts?: ApiFetchOptions) =>
    apiFetch<KnowledgeGapItem[]>(`/knowledge/gaps${qs(workspaceId, { agent_id: agentId })}`, { ...opts, method: "GET" }),
};
