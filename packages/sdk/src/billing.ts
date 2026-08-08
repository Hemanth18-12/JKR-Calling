import type { UsageSummary } from "@jkr/contracts";

import { type ApiFetchOptions, apiFetch } from "./client";

function qs(workspaceId: string) {
  return `?${new URLSearchParams({ workspace_id: workspaceId }).toString()}`;
}

export const billingApi = {
  usage: (workspaceId: string, opts?: ApiFetchOptions) =>
    apiFetch<UsageSummary>(`/billing/usage${qs(workspaceId)}`, { ...opts, method: "GET" }),
};
