import type {
  ConsentEventCreate,
  ConsentEventOut,
  ContactCreate,
  ContactDetail,
  ContactOut,
  SegmentCreate,
  SegmentOut,
  SuppressionCreate,
  SuppressionOut,
} from "@jkr/contracts";

import { type ApiFetchOptions, apiFetch } from "./client";

function qs(workspaceId: string) {
  return `?${new URLSearchParams({ workspace_id: workspaceId }).toString()}`;
}

export const contactsApi = {
  list: (workspaceId: string, opts?: ApiFetchOptions) =>
    apiFetch<ContactOut[]>(`/contacts${qs(workspaceId)}`, { ...opts, method: "GET" }),
  create: (workspaceId: string, data: ContactCreate, opts?: ApiFetchOptions) =>
    apiFetch<ContactOut>(`/contacts${qs(workspaceId)}`, { ...opts, method: "POST", body: data }),
  get: (workspaceId: string, contactId: string, opts?: ApiFetchOptions) =>
    apiFetch<ContactDetail>(`/contacts/${contactId}${qs(workspaceId)}`, { ...opts, method: "GET" }),
  recordConsent: (workspaceId: string, contactId: string, data: ConsentEventCreate, opts?: ApiFetchOptions) =>
    apiFetch<ConsentEventOut>(`/contacts/${contactId}/consent${qs(workspaceId)}`, { ...opts, method: "POST", body: data }),
  listConsent: (workspaceId: string, contactId: string, opts?: ApiFetchOptions) =>
    apiFetch<ConsentEventOut[]>(`/contacts/${contactId}/consent${qs(workspaceId)}`, { ...opts, method: "GET" }),
  suppress: (workspaceId: string, data: SuppressionCreate, opts?: ApiFetchOptions) =>
    apiFetch<SuppressionOut>(`/contacts/suppression${qs(workspaceId)}`, { ...opts, method: "POST", body: data }),
  listSuppression: (workspaceId: string, opts?: ApiFetchOptions) =>
    apiFetch<SuppressionOut[]>(`/contacts/suppression/list${qs(workspaceId)}`, { ...opts, method: "GET" }),
  createSegment: (workspaceId: string, data: SegmentCreate, opts?: ApiFetchOptions) =>
    apiFetch<SegmentOut>(`/contacts/segments${qs(workspaceId)}`, { ...opts, method: "POST", body: data }),
  listSegments: (workspaceId: string, opts?: ApiFetchOptions) =>
    apiFetch<SegmentOut[]>(`/contacts/segments/list${qs(workspaceId)}`, { ...opts, method: "GET" }),
};
