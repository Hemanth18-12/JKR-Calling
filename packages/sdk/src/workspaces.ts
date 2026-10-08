import type {
  AcceptInvitationRequest,
  AcceptInvitationResponse,
  InvitationDetailsPublic,
  MemberInvite,
  MemberOut,
  MemberUpdate,
  PendingInvitationOut,
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
  resendInvitation: (workspaceId: string, invitationId: string, opts?: ApiFetchOptions) =>
    apiFetch<MemberOut>(`/workspaces/${workspaceId}/invitations/${invitationId}/resend`, { ...opts, method: "POST" }),
  revokeInvitation: (workspaceId: string, invitationId: string, opts?: ApiFetchOptions) =>
    apiFetch<void>(`/workspaces/${workspaceId}/invitations/${invitationId}`, { ...opts, method: "DELETE" }),
  updateMember: (workspaceId: string, memberId: string, data: MemberUpdate, opts?: ApiFetchOptions) =>
    apiFetch<MemberOut>(`/workspaces/${workspaceId}/members/${memberId}`, { ...opts, method: "PATCH", body: data }),
  listPendingInvitations: (opts?: ApiFetchOptions) =>
    apiFetch<PendingInvitationOut[]>("/workspaces/invitations/pending", { ...opts, method: "GET" }),
  getInvitationDetails: (token: string, opts?: ApiFetchOptions) =>
    apiFetch<InvitationDetailsPublic>(`/workspaces/invitations/details?token=${encodeURIComponent(token)}`, {
      ...opts,
      method: "GET",
    }),
  acceptInvitation: (data: AcceptInvitationRequest, opts?: ApiFetchOptions) =>
    apiFetch<AcceptInvitationResponse>("/workspaces/invitations/accept", { ...opts, method: "POST", body: data }),
  declineInvitation: (invitationId: string, opts?: ApiFetchOptions) =>
    apiFetch<void>(`/workspaces/invitations/${invitationId}/decline`, { ...opts, method: "POST" }),
};
