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
  status: z.string(),
  requires_oauth: z.boolean(),
});
export type IntegrationCatalogItem = z.infer<typeof IntegrationCatalogItem>;
