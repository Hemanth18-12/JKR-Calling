/**
 * Mirrors services/api/app/modules/identity/schemas.py — kept in sync by
 * hand for this pass (docs/DECISIONS/0001-tooling-and-monorepo.md).
 */
import { z } from "zod";

export const SignupRequest = z.object({
  email: z.string().email(),
  full_name: z.string().min(1).max(200),
  password: z.string().min(10).max(200),
});
export type SignupRequest = z.infer<typeof SignupRequest>;

export const LoginRequest = z.object({
  email: z.string().email(),
  password: z.string().min(1),
});
export type LoginRequest = z.infer<typeof LoginRequest>;

export const UserOut = z.object({
  id: z.string().uuid(),
  email: z.string(),
  full_name: z.string(),
  is_platform_super_admin: z.boolean(),
  created_at: z.string(),
});
export type UserOut = z.infer<typeof UserOut>;

export const WorkspaceMembershipOut = z.object({
  workspace_id: z.string().uuid(),
  workspace_name: z.string(),
  workspace_slug: z.string(),
  role_key: z.string(),
});
export type WorkspaceMembershipOut = z.infer<typeof WorkspaceMembershipOut>;

export const MeResponse = z.object({
  user: UserOut,
  memberships: z.array(WorkspaceMembershipOut),
  active_workspace_id: z.string().uuid().nullable(),
  google_oauth_enabled: z.boolean(),
});
export type MeResponse = z.infer<typeof MeResponse>;

export const ApiError = z.object({
  error: z.object({
    code: z.number(),
    message: z.string(),
    details: z.record(z.unknown()).optional(),
  }),
});
export type ApiError = z.infer<typeof ApiError>;
