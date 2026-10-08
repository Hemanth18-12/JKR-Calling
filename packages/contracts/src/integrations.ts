/**
 * Mirrors services/api/app/modules/integrations/schemas.py.
 */
import { z } from "zod";

export const WebhookEndpointCreate = z.object({
  url: z.string().min(1).max(1000),
  secret: z.string().min(8).max(200),
  event_types: z.array(z.string()).default(["call.completed"]),
});
export type WebhookEndpointCreate = z.infer<typeof WebhookEndpointCreate>;

export const WebhookEndpointOut = z.object({
  id: z.string().uuid(),
  url: z.string(),
  event_types: z.array(z.string()),
  is_active: z.boolean(),
  created_at: z.string(),
});
export type WebhookEndpointOut = z.infer<typeof WebhookEndpointOut>;

export const WebhookDeliveryOut = z.object({
  id: z.string().uuid(),
  event_type: z.string(),
  status: z.string(),
  attempt_count: z.number(),
  response_status: z.number().nullable(),
  last_attempted_at: z.string().nullable(),
  created_at: z.string(),
});
export type WebhookDeliveryOut = z.infer<typeof WebhookDeliveryOut>;

export const IntegrationCatalogItem = z.object({
  type: z.string(),
  label: z.string(),
  description: z.string().nullable().optional(),
  status: z.string(),
  requires_oauth: z.boolean(),
  connected_account: z.string().nullable().optional(),
  external_url: z.string().nullable().optional(),
  last_synced_at: z.string().nullable().optional(),
  last_error: z.string().nullable().optional(),
});
export type IntegrationCatalogItem = z.infer<typeof IntegrationCatalogItem>;

export const CrmVerifyRequest = z.object({
  crm_type: z.string().default("hubspot"),
  hubspot_token: z.string().optional(),
  webhook_url: z.string().optional(),
  crm_name: z.string().default("HubSpot"),
});
export type CrmVerifyRequest = z.infer<typeof CrmVerifyRequest>;

export const IntegrationTestResult = z.object({
  status: z.string(),
  integration_type: z.string(),
  message: z.string(),
  details: z.record(z.any()).default({}),
  tested_at: z.string(),
});
export type IntegrationTestResult = z.infer<typeof IntegrationTestResult>;
