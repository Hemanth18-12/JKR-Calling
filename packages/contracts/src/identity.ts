/**
 * Mirrors services/api/app/modules/identity/schemas.py — kept in sync by
 * hand for this pass (docs/DECISIONS/0001-tooling-and-monorepo.md).
 */
import { z } from "zod";

// RFC 5322 compliant regex requiring valid domain and TLD (at least 2 letters, e.g. name@domain.com)
const emailRegex = /^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$/;

export const SignupRequest = z.object({
  email: z
    .string()
    .trim()
    .toLowerCase()
    .min(5, "Email is too short")
    .max(254, "Email is too long")
    .regex(emailRegex, "Please enter a valid email address with a valid domain (e.g. name@domain.com)"),
  full_name: z.string().min(1, "Full name is required").max(200),
  password: z.string().min(10, "Password must be at least 10 characters").max(200),
});
export type SignupRequest = z.infer<typeof SignupRequest>;

export const LoginRequest = z.object({
  email: z
    .string()
    .trim()
    .toLowerCase()
    .min(5, "Email is too short")
    .max(254, "Email is too long")
    .regex(emailRegex, "Please enter a valid email address with a valid domain (e.g. name@domain.com)"),
  password: z.string().min(1, "Password is required"),
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

export const VerifyOtpRequest = z.object({
  email: z
    .string()
    .trim()
    .toLowerCase()
    .min(5, "Email is too short")
    .max(254, "Email is too long")
    .regex(emailRegex, "Please enter a valid email address with a valid domain"),
  purpose: z.enum(["signup", "login"]),
  code: z.string().trim().regex(/^\d{6}$/, "Verification code must be exactly 6 digits"),
});
export type VerifyOtpRequest = z.infer<typeof VerifyOtpRequest>;

export const ResendOtpRequest = z.object({
  email: z
    .string()
    .trim()
    .toLowerCase()
    .min(5, "Email is too short")
    .max(254, "Email is too long")
    .regex(emailRegex, "Please enter a valid email address with a valid domain"),
  purpose: z.enum(["signup", "login"]),
});
export type ResendOtpRequest = z.infer<typeof ResendOtpRequest>;

export const OtpRequiredResponse = z.object({
  status: z.literal("otp_required"),
  email: z.string(),
  purpose: z.enum(["signup", "login"]),
  message: z.string(),
});
export type OtpRequiredResponse = z.infer<typeof OtpRequiredResponse>;

export const GoogleOAuthUrlResponse = z.object({
  url: z.string(),
  enabled: z.boolean(),
});
export type GoogleOAuthUrlResponse = z.infer<typeof GoogleOAuthUrlResponse>;

export const GoogleOAuthCallbackRequest = z.object({
  code: z.string().min(1, "Authorization code is required"),
  redirect_uri: z.string().optional(),
});
export type GoogleOAuthCallbackRequest = z.infer<typeof GoogleOAuthCallbackRequest>;

export const ApiError = z.object({
  error: z.object({
    code: z.number(),
    message: z.string(),
    details: z.record(z.unknown()).optional(),
  }),
});
export type ApiError = z.infer<typeof ApiError>;

