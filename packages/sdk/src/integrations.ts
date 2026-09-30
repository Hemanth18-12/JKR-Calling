import type { IntegrationCatalogItem, WebhookDeliveryOut, WebhookEndpointCreate, WebhookEndpointOut } from "@jkr/contracts";

import { type ApiFetchOptions, apiFetch } from "./client";

function qs(workspaceId: string, extra?: Record<string, string>) {
  const params = new URLSearchParams({ workspace_id: workspaceId, ...(extra || {}) });
  return `?${params.toString()}`;
}

export interface OAuthUrlResponse {
  auth_url: string | null;
  configured: boolean;
  message?: string;
}

export const integrationsApi = {
  catalog: (workspaceId: string, opts?: ApiFetchOptions) =>
    apiFetch<IntegrationCatalogItem[]>(`/integrations${qs(workspaceId)}`, { ...opts, method: "GET" }),

  getGoogleAuthUrl: (workspaceId: string, integrationType: string = "google_calendar", opts?: ApiFetchOptions) =>
    apiFetch<OAuthUrlResponse>(`/integrations/google/auth-url${qs(workspaceId, { integration_type: integrationType })}`, { ...opts, method: "GET" }),

  connectGoogleCalendar: (workspaceId: string, data: { email?: string; calendar_id?: string; access_token?: string; code?: string }, opts?: ApiFetchOptions) =>
    apiFetch<{ is_connected: boolean; email?: string }>(`/integrations/google-calendar/connect${qs(workspaceId)}`, { ...opts, method: "POST", body: data }),

  connectGoogleSheets: (workspaceId: string, data: { email?: string; spreadsheet_id?: string; sheet_name?: string; access_token?: string; code?: string }, opts?: ApiFetchOptions) =>
    apiFetch<{ is_connected: boolean; email?: string }>(`/integrations/google-sheets/connect${qs(workspaceId)}`, { ...opts, method: "POST", body: data }),

  connectMeta: (workspaceId: string, data: { page_id: string; page_name?: string; access_token?: string }, opts?: ApiFetchOptions) =>
    apiFetch<{ status: string; page_id: string }>(`/integrations/meta/connect${qs(workspaceId)}`, { ...opts, method: "POST", body: data }),

  connectWhatsapp: (workspaceId: string, data: { phone_number: string; waba_id?: string; access_token?: string }, opts?: ApiFetchOptions) =>
    apiFetch<{ status: string; phone_number: string }>(`/integrations/whatsapp/connect${qs(workspaceId)}`, { ...opts, method: "POST", body: data }),

  disconnect: (workspaceId: string, integrationType: string, opts?: ApiFetchOptions) =>
    apiFetch<{ status: string; type: string }>(`/integrations/${integrationType}/disconnect${qs(workspaceId)}`, { ...opts, method: "POST" }),

  verifyN8n: (workspaceId: string, data: { instance_url: string; api_key?: string; webhook_url?: string }, opts?: ApiFetchOptions) =>
    apiFetch<{ status: string; instance_url: string }>(`/integrations/n8n/verify${qs(workspaceId)}`, { ...opts, method: "POST", body: data }),

  verifyCrm: (workspaceId: string, data: { webhook_url: string; crm_name?: string }, opts?: ApiFetchOptions) =>
    apiFetch<{ status: string; crm_name: string; webhook_url: string }>(`/integrations/crm/verify${qs(workspaceId)}`, { ...opts, method: "POST", body: data }),

  listWebhooks: (workspaceId: string, opts?: ApiFetchOptions) =>
    apiFetch<WebhookEndpointOut[]>(`/integrations/webhooks${qs(workspaceId)}`, { ...opts, method: "GET" }),

  createWebhook: (workspaceId: string, data: WebhookEndpointCreate, opts?: ApiFetchOptions) =>
    apiFetch<WebhookEndpointOut>(`/integrations/webhooks${qs(workspaceId)}`, { ...opts, method: "POST", body: data }),

  deactivateWebhook: (workspaceId: string, endpointId: string, opts?: ApiFetchOptions) =>
    apiFetch<WebhookEndpointOut>(`/integrations/webhooks/${endpointId}/deactivate${qs(workspaceId)}`, { ...opts, method: "POST" }),

  listDeliveries: (workspaceId: string, endpointId: string, opts?: ApiFetchOptions) =>
    apiFetch<WebhookDeliveryOut[]>(`/integrations/webhooks/${endpointId}/deliveries${qs(workspaceId)}`, { ...opts, method: "GET" }),
};
