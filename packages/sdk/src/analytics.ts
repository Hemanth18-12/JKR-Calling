import type { BusinessOverview, CallAnalytics, ConversationQuality, ProviderAnalytics } from "@jkr/contracts";

import { type ApiFetchOptions, apiFetch } from "./client";

function qs(workspaceId: string) {
  return `?${new URLSearchParams({ workspace_id: workspaceId }).toString()}`;
}

export const analyticsApi = {
  overview: (workspaceId: string, opts?: ApiFetchOptions) =>
    apiFetch<BusinessOverview>(`/analytics/overview${qs(workspaceId)}`, { ...opts, method: "GET" }),
  calls: (workspaceId: string, opts?: ApiFetchOptions) =>
    apiFetch<CallAnalytics>(`/analytics/calls${qs(workspaceId)}`, { ...opts, method: "GET" }),
  conversationQuality: (workspaceId: string, opts?: ApiFetchOptions) =>
    apiFetch<ConversationQuality>(`/analytics/conversation-quality${qs(workspaceId)}`, { ...opts, method: "GET" }),
  providers: (workspaceId: string, opts?: ApiFetchOptions) =>
    apiFetch<ProviderAnalytics>(`/analytics/providers${qs(workspaceId)}`, { ...opts, method: "GET" }),
};
