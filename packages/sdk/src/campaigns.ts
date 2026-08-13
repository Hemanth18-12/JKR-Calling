import type {
  AddContactsRequest,
  CampaignAttemptOut,
  CampaignContactOut,
  CampaignCreate,
  CampaignDetail,
  CampaignOut,
  CampaignScheduleOut,
  DryRunResponse,
} from "@jkr/contracts";

import { type ApiFetchOptions, apiFetch } from "./client";

function qs(workspaceId: string) {
  return `?${new URLSearchParams({ workspace_id: workspaceId }).toString()}`;
}

export const campaignsApi = {
  list: (workspaceId: string, opts?: ApiFetchOptions) =>
    apiFetch<CampaignOut[]>(`/campaigns${qs(workspaceId)}`, { ...opts, method: "GET" }),
  create: (workspaceId: string, data: CampaignCreate, opts?: ApiFetchOptions) =>
    apiFetch<CampaignOut>(`/campaigns${qs(workspaceId)}`, { ...opts, method: "POST", body: data }),
  get: (workspaceId: string, campaignId: string, opts?: ApiFetchOptions) =>
    apiFetch<CampaignDetail>(`/campaigns/${campaignId}${qs(workspaceId)}`, { ...opts, method: "GET" }),
  updateSchedule: (
    workspaceId: string, campaignId: string,
    data: { calling_window_start?: string | null; calling_window_end?: string | null; days_of_week?: number[] | null },
    opts?: ApiFetchOptions
  ) => apiFetch<CampaignScheduleOut>(`/campaigns/${campaignId}/schedule${qs(workspaceId)}`, { ...opts, method: "PATCH", body: data }),
  addContacts: (workspaceId: string, campaignId: string, data: AddContactsRequest, opts?: ApiFetchOptions) =>
    apiFetch<{ added: number }>(`/campaigns/${campaignId}/contacts${qs(workspaceId)}`, { ...opts, method: "POST", body: data }),
  listContacts: (workspaceId: string, campaignId: string, opts?: ApiFetchOptions) =>
    apiFetch<CampaignContactOut[]>(`/campaigns/${campaignId}/contacts${qs(workspaceId)}`, { ...opts, method: "GET" }),
  listAttempts: (workspaceId: string, campaignId: string, campaignContactId: string, opts?: ApiFetchOptions) =>
    apiFetch<CampaignAttemptOut[]>(`/campaigns/${campaignId}/contacts/${campaignContactId}/attempts${qs(workspaceId)}`, {
      ...opts, method: "GET",
    }),
  dryRun: (workspaceId: string, campaignId: string, opts?: ApiFetchOptions) =>
    apiFetch<DryRunResponse>(`/campaigns/${campaignId}/dry-run${qs(workspaceId)}`, { ...opts, method: "POST" }),
  launch: (workspaceId: string, campaignId: string, opts?: ApiFetchOptions) =>
    apiFetch<CampaignOut>(`/campaigns/${campaignId}/launch${qs(workspaceId)}`, { ...opts, method: "POST" }),
  pause: (workspaceId: string, campaignId: string, opts?: ApiFetchOptions) =>
    apiFetch<CampaignOut>(`/campaigns/${campaignId}/pause${qs(workspaceId)}`, { ...opts, method: "POST" }),
  cancel: (workspaceId: string, campaignId: string, opts?: ApiFetchOptions) =>
    apiFetch<CampaignOut>(`/campaigns/${campaignId}/cancel${qs(workspaceId)}`, { ...opts, method: "POST" }),
  delete: (workspaceId: string, campaignId: string, opts?: ApiFetchOptions) =>
    apiFetch<void>(`/campaigns/${campaignId}${qs(workspaceId)}`, { ...opts, method: "DELETE" }),
};

