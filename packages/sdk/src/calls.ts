import type { CallDetail, CallListItem, EndCallResponse, TestCallCreate, TestCallStarted, UserTurnResponse } from "@jkr/contracts";

import { type ApiFetchOptions, apiBaseUrl, apiFetch } from "./client";

function qs(workspaceId: string) {
  return `?${new URLSearchParams({ workspace_id: workspaceId }).toString()}`;
}

export const callsApi = {
  startTest: (workspaceId: string, data: TestCallCreate, opts?: ApiFetchOptions) =>
    apiFetch<TestCallStarted>(`/calls/test${qs(workspaceId)}`, { ...opts, method: "POST", body: data }),
  submitUserTurn: (workspaceId: string, callId: string, text: string, opts?: ApiFetchOptions) =>
    apiFetch<UserTurnResponse>(`/calls/${callId}/user-turn${qs(workspaceId)}`, {
      ...opts,
      method: "POST",
      body: { text },
    }),
  end: (workspaceId: string, callId: string, opts?: ApiFetchOptions) =>
    apiFetch<EndCallResponse>(`/calls/${callId}/end${qs(workspaceId)}`, { ...opts, method: "POST" }),
  get: (workspaceId: string, callId: string, opts?: ApiFetchOptions) =>
    apiFetch<CallDetail>(`/calls/${callId}${qs(workspaceId)}`, { ...opts, method: "GET" }),
  list: (workspaceId: string, status?: string, opts?: ApiFetchOptions) =>
    apiFetch<CallListItem[]>(`/calls${qs(workspaceId)}${status ? `&status=${status}` : ""}`, { ...opts, method: "GET" }),
  eventsUrl: (workspaceId: string, callId: string) => `${apiBaseUrl()}/api/v1/calls/${callId}/events${qs(workspaceId)}`,
};
