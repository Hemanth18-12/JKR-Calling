import type {
  AgentCreate,
  AgentDetail,
  AgentOut,
  AgentUpdate,
  AgentVersionDetail,
  AgentVersionOut,
  AgentVersionUpdate,
  ConversationPolicyOut,
  ConversationPolicyUpdate,
  PersonaTemplateOut,
  PronunciationEntryCreate,
  PronunciationEntryOut,
  VoicePersonaOut,
  VoicePersonaUpdate,
} from "@jkr/contracts";

import { type ApiFetchOptions, apiFetch } from "./client";

function qs(workspaceId: string, extra?: Record<string, string>) {
  const params = new URLSearchParams({ workspace_id: workspaceId, ...extra });
  return `?${params.toString()}`;
}

export const agentsApi = {
  personaTemplates: (workspaceId: string, opts?: ApiFetchOptions) =>
    apiFetch<PersonaTemplateOut[]>(`/agents/persona-templates${qs(workspaceId)}`, { ...opts, method: "GET" }),
  list: (workspaceId: string, opts?: ApiFetchOptions) =>
    apiFetch<AgentOut[]>(`/agents${qs(workspaceId)}`, { ...opts, method: "GET" }),
  create: (workspaceId: string, data: AgentCreate, opts?: ApiFetchOptions) =>
    apiFetch<AgentOut>(`/agents${qs(workspaceId)}`, { ...opts, method: "POST", body: data }),
  get: (workspaceId: string, agentId: string, opts?: ApiFetchOptions) =>
    apiFetch<AgentDetail>(`/agents/${agentId}${qs(workspaceId)}`, { ...opts, method: "GET" }),
  update: (workspaceId: string, agentId: string, data: AgentUpdate, opts?: ApiFetchOptions) =>
    apiFetch<AgentOut>(`/agents/${agentId}${qs(workspaceId)}`, { ...opts, method: "PATCH", body: data }),
  createVersion: (workspaceId: string, agentId: string, cloneFromVersionId?: string, opts?: ApiFetchOptions) =>
    apiFetch<AgentVersionOut>(
      `/agents/${agentId}/versions${qs(workspaceId, cloneFromVersionId ? { clone_from_version_id: cloneFromVersionId } : undefined)}`,
      { ...opts, method: "POST" }
    ),
  getVersion: (workspaceId: string, agentId: string, versionId: string, opts?: ApiFetchOptions) =>
    apiFetch<AgentVersionDetail>(`/agents/${agentId}/versions/${versionId}${qs(workspaceId)}`, { ...opts, method: "GET" }),
  updateVersion: (workspaceId: string, agentId: string, versionId: string, data: AgentVersionUpdate, opts?: ApiFetchOptions) =>
    apiFetch<AgentVersionOut>(`/agents/${agentId}/versions/${versionId}${qs(workspaceId)}`, {
      ...opts,
      method: "PATCH",
      body: data,
    }),
  updateVoice: (workspaceId: string, agentId: string, versionId: string, data: VoicePersonaUpdate, opts?: ApiFetchOptions) =>
    apiFetch<VoicePersonaOut>(`/agents/${agentId}/versions/${versionId}/voice${qs(workspaceId)}`, {
      ...opts,
      method: "PATCH",
      body: data,
    }),
  updatePolicy: (workspaceId: string, agentId: string, versionId: string, data: ConversationPolicyUpdate, opts?: ApiFetchOptions) =>
    apiFetch<ConversationPolicyOut>(`/agents/${agentId}/versions/${versionId}/policy${qs(workspaceId)}`, {
      ...opts,
      method: "PATCH",
      body: data,
    }),
  addPronunciation: (workspaceId: string, agentId: string, versionId: string, data: PronunciationEntryCreate, opts?: ApiFetchOptions) =>
    apiFetch<PronunciationEntryOut>(`/agents/${agentId}/versions/${versionId}/pronunciation${qs(workspaceId)}`, {
      ...opts,
      method: "POST",
      body: data,
    }),
  deletePronunciation: (workspaceId: string, agentId: string, versionId: string, entryId: string, opts?: ApiFetchOptions) =>
    apiFetch<void>(`/agents/${agentId}/versions/${versionId}/pronunciation/${entryId}${qs(workspaceId)}`, {
      ...opts,
      method: "DELETE",
    }),
  publishVersion: (workspaceId: string, agentId: string, versionId: string, opts?: ApiFetchOptions) =>
    apiFetch<AgentVersionOut>(`/agents/${agentId}/versions/${versionId}/publish${qs(workspaceId)}`, {
      ...opts,
      method: "POST",
    }),
};
