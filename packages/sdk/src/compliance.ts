import type { AuditLogEntryOut, ComplianceOverview } from "@jkr/contracts";

import { type ApiFetchOptions, apiFetch } from "./client";

function qs(workspaceId: string) {
  return `?${new URLSearchParams({ workspace_id: workspaceId }).toString()}`;
}

export const complianceApi = {
  overview: (workspaceId: string, opts?: ApiFetchOptions) =>
    apiFetch<ComplianceOverview>(`/compliance/overview${qs(workspaceId)}`, { ...opts, method: "GET" }),
  auditLog: (workspaceId: string, limit = 50, opts?: ApiFetchOptions) =>
    apiFetch<AuditLogEntryOut[]>(`/compliance/audit-log${qs(workspaceId)}&limit=${limit}`, { ...opts, method: "GET" }),
};
