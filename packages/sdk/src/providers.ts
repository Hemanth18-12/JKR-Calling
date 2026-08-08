import type { ProviderAccountOut, ProviderCatalogEntry } from "@jkr/contracts";

import { type ApiFetchOptions, apiFetch } from "./client";

function qs(workspaceId: string) {
  return `?${new URLSearchParams({ workspace_id: workspaceId }).toString()}`;
}

export const providersApi = {
  catalog: (workspaceId: string, opts?: ApiFetchOptions) =>
    apiFetch<ProviderCatalogEntry[]>(`/providers/catalog${qs(workspaceId)}`, { ...opts, method: "GET" }),
  listAccounts: (workspaceId: string, opts?: ApiFetchOptions) =>
    apiFetch<ProviderAccountOut[]>(`/providers/accounts${qs(workspaceId)}`, { ...opts, method: "GET" }),
};
