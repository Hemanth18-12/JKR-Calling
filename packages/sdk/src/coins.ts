import type {
  AdminApproveReject,
  AdminDashboardOverview,
  CoinTier,
  CoinTopupRequestCreate,
  CoinTopupRequestOut,
  CoinTransactionOut,
  CoinWalletOut,
} from "@jkr/contracts";

import { type ApiFetchOptions, apiFetch } from "./client";

function qs(workspaceId: string) {
  return `?${new URLSearchParams({ workspace_id: workspaceId }).toString()}`;
}

export const coinsApi = {
  getWallet: (workspaceId: string, opts?: ApiFetchOptions) =>
    apiFetch<CoinWalletOut>(`/coins/wallet${qs(workspaceId)}`, { ...opts, method: "GET" }),

  getTiers: (workspaceId: string, opts?: ApiFetchOptions) =>
    apiFetch<CoinTier[]>(`/coins/tiers${qs(workspaceId)}`, { ...opts, method: "GET" }),

  getTransactions: (workspaceId: string, opts?: ApiFetchOptions) =>
    apiFetch<CoinTransactionOut[]>(`/coins/transactions${qs(workspaceId)}`, { ...opts, method: "GET" }),

  getTopupRequests: (workspaceId: string, opts?: ApiFetchOptions) =>
    apiFetch<CoinTopupRequestOut[]>(`/coins/topup-requests${qs(workspaceId)}`, { ...opts, method: "GET" }),

  createTopupRequest: (workspaceId: string, payload: CoinTopupRequestCreate, opts?: ApiFetchOptions) =>
    apiFetch<CoinTopupRequestOut>(`/coins/topup-requests${qs(workspaceId)}`, {
      ...opts,
      method: "POST",
      body: payload,
    }),
};

export const adminCoinsApi = {
  listTopupRequests: (status?: string, opts?: ApiFetchOptions) => {
    const q = status ? `?status=${encodeURIComponent(status)}` : "";
    return apiFetch<CoinTopupRequestOut[]>(`/admin/coins/topup-requests${q}`, { ...opts, method: "GET" });
  },

  approveTopup: (requestId: string, payload?: AdminApproveReject, opts?: ApiFetchOptions) =>
    apiFetch<CoinTopupRequestOut>(`/admin/coins/topup-requests/${requestId}/approve`, {
      ...opts,
      method: "POST",
      body: payload ?? {},
    }),

  rejectTopup: (requestId: string, payload?: AdminApproveReject, opts?: ApiFetchOptions) =>
    apiFetch<CoinTopupRequestOut>(`/admin/coins/topup-requests/${requestId}/reject`, {
      ...opts,
      method: "POST",
      body: payload ?? {},
    }),

  getOverview: (opts?: ApiFetchOptions) =>
    apiFetch<AdminDashboardOverview>("/admin/coins/overview", {
      ...opts,
      method: "GET",
    }),
};
