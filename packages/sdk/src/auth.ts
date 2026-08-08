import type { LoginRequest, MeResponse, SignupRequest, UserOut } from "@jkr/contracts";

import { type ApiFetchOptions, apiFetch } from "./client";

export const authApi = {
  signup: (data: SignupRequest, opts?: ApiFetchOptions) =>
    apiFetch<UserOut>("/auth/signup", { ...opts, method: "POST", body: data }),
  login: (data: LoginRequest, opts?: ApiFetchOptions) =>
    apiFetch<UserOut>("/auth/login", { ...opts, method: "POST", body: data }),
  logout: (opts?: ApiFetchOptions) => apiFetch<void>("/auth/logout", { ...opts, method: "POST" }),
  me: (opts?: ApiFetchOptions) => apiFetch<MeResponse>("/auth/me", { ...opts, method: "GET" }),
  setActiveWorkspace: (workspaceId: string, opts?: ApiFetchOptions) =>
    apiFetch<MeResponse>("/auth/session/active-workspace", {
      ...opts,
      method: "POST",
      body: { workspace_id: workspaceId },
    }),
};
