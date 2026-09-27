import type {
  LoginRequest,
  MeResponse,
  OtpRequiredResponse,
  ResendOtpRequest,
  SignupRequest,
  UserOut,
  VerifyOtpRequest,
} from "@jkr/contracts";

import { type ApiFetchOptions, apiFetch } from "./client";

export const authApi = {
  signup: (data: SignupRequest, opts?: ApiFetchOptions) =>
    apiFetch<OtpRequiredResponse | UserOut>("/auth/signup", { ...opts, method: "POST", body: data }),
  login: (data: LoginRequest, opts?: ApiFetchOptions) =>
    apiFetch<OtpRequiredResponse | UserOut>("/auth/login", { ...opts, method: "POST", body: data }),
  verifyOtp: (data: VerifyOtpRequest, opts?: ApiFetchOptions) =>
    apiFetch<UserOut>("/auth/verify-otp", { ...opts, method: "POST", body: data }),
  resendOtp: (data: ResendOtpRequest, opts?: ApiFetchOptions) =>
    apiFetch<{ status: string; message: string }>("/auth/resend-otp", { ...opts, method: "POST", body: data }),
  logout: (opts?: ApiFetchOptions) => apiFetch<void>("/auth/logout", { ...opts, method: "POST" }),
  me: (opts?: ApiFetchOptions) => apiFetch<MeResponse>("/auth/me", { ...opts, method: "GET" }),
  setActiveWorkspace: (workspaceId: string, opts?: ApiFetchOptions) =>
    apiFetch<MeResponse>("/auth/session/active-workspace", {
      ...opts,
      method: "POST",
      body: { workspace_id: workspaceId },
    }),
};

