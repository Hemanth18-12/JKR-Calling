import type { AppointmentOut, FollowUpTaskOut, HumanHandoffOut } from "@jkr/contracts";

import { type ApiFetchOptions, apiFetch } from "./client";

function qs(workspaceId: string, status?: string) {
  const params = new URLSearchParams({ workspace_id: workspaceId });
  if (status) params.set("status", status);
  return `?${params.toString()}`;
}

export const operationsApi = {
  listFollowUps: (workspaceId: string, status?: string, opts?: ApiFetchOptions) =>
    apiFetch<FollowUpTaskOut[]>(`/follow-ups${qs(workspaceId, status)}`, { ...opts, method: "GET" }),
  completeFollowUp: (workspaceId: string, taskId: string, opts?: ApiFetchOptions) =>
    apiFetch<FollowUpTaskOut>(`/follow-ups/${taskId}/complete${qs(workspaceId)}`, { ...opts, method: "POST" }),
  listHandoffs: (workspaceId: string, status?: string, opts?: ApiFetchOptions) =>
    apiFetch<HumanHandoffOut[]>(`/handoffs${qs(workspaceId, status)}`, { ...opts, method: "GET" }),
  actOnHandoff: (workspaceId: string, handoffId: string, action: "accept" | "resolve" | "abandon", opts?: ApiFetchOptions) =>
    apiFetch<HumanHandoffOut>(`/handoffs/${handoffId}/action${qs(workspaceId)}`, { ...opts, method: "POST", body: { action } }),
  listAppointments: (workspaceId: string, status?: string, opts?: ApiFetchOptions) =>
    apiFetch<AppointmentOut[]>(`/appointments${qs(workspaceId, status)}`, { ...opts, method: "GET" }),
  cancelAppointment: (workspaceId: string, appointmentId: string, opts?: ApiFetchOptions) =>
    apiFetch<AppointmentOut>(`/appointments/${appointmentId}/cancel${qs(workspaceId)}`, { ...opts, method: "POST" }),
};
