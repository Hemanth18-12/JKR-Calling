import type { AgentToolOut, ToolDefinitionOut, ToolExecutionOut } from "@jkr/contracts";

import { type ApiFetchOptions, apiFetch } from "./client";

function qs(workspaceId: string) {
  return `?${new URLSearchParams({ workspace_id: workspaceId }).toString()}`;
}

export const toolsApi = {
  list: (workspaceId: string, opts?: ApiFetchOptions) =>
    apiFetch<ToolDefinitionOut[]>(`/tools${qs(workspaceId)}`, { ...opts, method: "GET" }),
  setEnabled: (workspaceId: string, definitionId: string, isEnabled: boolean, opts?: ApiFetchOptions) =>
    apiFetch<ToolDefinitionOut>(`/tools/${definitionId}${qs(workspaceId)}`, { ...opts, method: "PATCH", body: { is_enabled: isEnabled } }),
  listAgentTools: (workspaceId: string, agentVersionId: string, opts?: ApiFetchOptions) =>
    apiFetch<AgentToolOut[]>(`/tools/agent-versions/${agentVersionId}${qs(workspaceId)}`, { ...opts, method: "GET" }),
  setAgentToolEnabled: (workspaceId: string, agentVersionId: string, toolDefinitionId: string, enabled: boolean, opts?: ApiFetchOptions) =>
    apiFetch<AgentToolOut>(`/tools/agent-versions/${agentVersionId}/${toolDefinitionId}${qs(workspaceId)}`, {
      ...opts, method: "PATCH", body: { enabled },
    }),
  listExecutionsForCall: (workspaceId: string, callSessionId: string, opts?: ApiFetchOptions) =>
    apiFetch<ToolExecutionOut[]>(`/tools/executions/by-call/${callSessionId}${qs(workspaceId)}`, { ...opts, method: "GET" }),
};
