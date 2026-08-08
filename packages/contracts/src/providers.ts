import { z } from "zod";

export const ProviderAccountOut = z.object({
  id: z.string().uuid(),
  kind: z.string(),
  name: z.string(),
  display_name: z.string(),
  is_default: z.boolean(),
  priority: z.number(),
  status: z.string(),
  region: z.string().nullable(),
  created_at: z.string(),
});
export type ProviderAccountOut = z.infer<typeof ProviderAccountOut>;

export const ProviderCatalogEntry = z.object({
  kind: z.string(),
  name: z.string(),
  label: z.string(),
  requires_credentials: z.boolean(),
  configured_env_vars: z.array(z.string()),
});
export type ProviderCatalogEntry = z.infer<typeof ProviderCatalogEntry>;
