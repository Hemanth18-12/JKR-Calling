/**
 * Mirrors services/api/app/modules/tenancy/schemas.py.
 */
import { z } from "zod";

export const WorkspaceCreate = z.object({
  name: z.string().min(1).max(200),
  slug: z
    .string()
    .min(1)
    .max(100)
    .regex(/^[a-z0-9][a-z0-9-]*[a-z0-9]$/, "lowercase letters, numbers and hyphens only"),
  timezone: z.string().default("Asia/Kolkata"),
  default_language: z.string().default("te-en-IN"),
});
export type WorkspaceCreate = z.infer<typeof WorkspaceCreate>;

export const WorkspaceUpdate = z.object({
  name: z.string().min(1).max(200).optional(),
  timezone: z.string().optional(),
  default_language: z.string().optional(),
  calling_window_start: z.string().optional(),
  calling_window_end: z.string().optional(),
  recording_retention_days: z.number().int().min(1).max(3650).optional(),
  transcript_retention_days: z.number().int().min(1).max(3650).optional(),
});
export type WorkspaceUpdate = z.infer<typeof WorkspaceUpdate>;

export const WorkspaceOut = z.object({
  id: z.string().uuid(),
  organization_id: z.string().uuid(),
  name: z.string(),
  slug: z.string(),
  timezone: z.string(),
  default_language: z.string(),
  calling_window_start: z.string(),
  calling_window_end: z.string(),
  identity_verified_at: z.string().nullable(),
  recording_retention_days: z.number(),
  transcript_retention_days: z.number(),
  is_demo: z.boolean(),
  created_at: z.string(),
});
export type WorkspaceOut = z.infer<typeof WorkspaceOut>;

export const WorkspaceListItem = WorkspaceOut.extend({ role_key: z.string() });
export type WorkspaceListItem = z.infer<typeof WorkspaceListItem>;

export const MemberInvite = z.object({
  email: z.string().email(),
  role_key: z.string(),
});
export type MemberInvite = z.infer<typeof MemberInvite>;

export const MemberUpdate = z.object({
  role_key: z.string().optional(),
  status: z.enum(["active", "invited", "suspended"]).optional(),
});
export type MemberUpdate = z.infer<typeof MemberUpdate>;

export const MemberOut = z.object({
  id: z.string().uuid(),
  user_id: z.string().uuid(),
  email: z.string(),
  full_name: z.string(),
  role_key: z.string(),
  status: z.string(),
  invited_at: z.string().nullable(),
  joined_at: z.string().nullable(),
});
export type MemberOut = z.infer<typeof MemberOut>;

export const ROLE_OPTIONS = [
  { key: "workspace_owner", label: "Owner" },
  { key: "workspace_admin", label: "Admin" },
  { key: "campaign_manager", label: "Campaign Manager" },
  { key: "sales_manager", label: "Sales Manager" },
  { key: "agent_operator", label: "Agent Operator" },
  { key: "analyst", label: "Analyst" },
  { key: "viewer", label: "Viewer" },
] as const;
