import type { LiveTestCallCreate, LiveTestCallStarted } from "@jkr/contracts";

import { type ApiFetchOptions, apiFetch } from "./client";

function qs(workspaceId: string) {
  return `?${new URLSearchParams({ workspace_id: workspaceId }).toString()}`;
}

export const liveCallApi = {
  start: (workspaceId: string, data: LiveTestCallCreate, opts?: ApiFetchOptions) =>
    apiFetch<LiveTestCallStarted>(`/live-call${qs(workspaceId)}`, { ...opts, method: "POST", body: data }),
};
