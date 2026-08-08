import type { IntegrationCatalogItem, WebhookDeliveryOut, WebhookEndpointCreate, WebhookEndpointOut } from "@jkr/contracts";

import { type ApiFetchOptions, apiFetch } from "./client";

function qs(workspaceId: string) {
  return `?${new URLSearchParams({ workspace_id: workspaceId }).toString()}`;
}

export const integrationsApi = {
  catalog: (workspaceId: string, opts?: ApiFetchOptions) =>
    apiFetch<IntegrationCatalogItem[]>(`/integrations${qs(workspaceId)}`, { ...opts, method: "GET" }),
  listWebhooks: (workspaceId: string, opts?: ApiFetchOptions) =>
    apiFetch<WebhookEndpointOut[]>(`/integrations/webhooks${qs(workspaceId)}`, { ...opts, method: "GET" }),
  createWebhook: (workspaceId: string, data: WebhookEndpointCreate, opts?: ApiFetchOptions) =>
    apiFetch<WebhookEndpointOut>(`/integrations/webhooks${qs(workspaceId)}`, { ...opts, method: "POST", body: data }),
  deactivateWebhook: (workspaceId: string, endpointId: string, opts?: ApiFetchOptions) =>
    apiFetch<WebhookEndpointOut>(`/integrations/webhooks/${endpointId}/deactivate${qs(workspaceId)}`, { ...opts, method: "POST" }),
  listDeliveries: (workspaceId: string, endpointId: string, opts?: ApiFetchOptions) =>
    apiFetch<WebhookDeliveryOut[]>(`/integrations/webhooks/${endpointId}/deliveries${qs(workspaceId)}`, { ...opts, method: "GET" }),
};
