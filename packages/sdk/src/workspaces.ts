import type {
  MemberInvite,
  MemberOut,
  MemberUpdate,
  WorkspaceCreate,
  WorkspaceListItem,
  WorkspaceOut,
  WorkspaceUpdate,
} from "@jkr/contracts";

import { type ApiFetchOptions, apiFetch } from "./client";

export const workspacesApi = {
  create: (data: WorkspaceCreate, opts?: ApiFetchOptions) =>
    apiFetch<WorkspaceOut>("/workspaces", { ...opts, method: "POST", body: data }),
  list: (opts?: ApiFetchOptions) => apiFetch<WorkspaceListItem[]>("/workspaces", { ...opts, method: "GET" }),
  get: (workspaceId: string, opts?: ApiFetchOptions) =>
    apiFetch<WorkspaceOut>(`/workspaces/${workspaceId}`, { ...opts, method: "GET" }),
  update: (workspaceId: string, data: WorkspaceUpdate, opts?: ApiFetchOptions) =>
    apiFetch<WorkspaceOut>(`/workspaces/${workspaceId}`, { ...opts, method: "PATCH", body: data }),
  listMembers: (workspaceId: string, opts?: ApiFetchOptions) =>
    apiFetch<MemberOut[]>(`/workspaces/${workspaceId}/members`, { ...opts, method: "GET" }),
  inviteMember: (workspaceId: string, data: MemberInvite, opts?: ApiFetchOptions) =>
    apiFetch<MemberOut>(`/workspaces/${workspaceId}/members`, { ...opts, method: "POST", body: data }),
  updateMember: (workspaceId: string, memberId: string, data: MemberUpdate, opts?: ApiFetchOptions) =>
    apiFetch<MemberOut>(`/workspaces/${workspaceId}/members/${memberId}`, { ...opts, method: "PATCH", body: data }),
};
