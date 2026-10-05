import type {
  StartWidgetSessionRequest,
  StartWidgetSessionResponse,
  WidgetConfigResponse,
  WidgetMessageRequest,
  WidgetMessageResponse,
} from "@jkr/contracts";

import { type ApiFetchOptions, apiFetch } from "./client";

export const widgetApi = {
  getConfig: (agentId: string, opts?: ApiFetchOptions) =>
    apiFetch<WidgetConfigResponse>(`/widget/config/${agentId}`, { ...opts, method: "GET" }),

  startSession: (payload: StartWidgetSessionRequest, opts?: ApiFetchOptions) =>
    apiFetch<StartWidgetSessionResponse>("/widget/session", {
      ...opts,
      method: "POST",
      body: payload,
    }),

  sendMessage: (sessionId: string, payload: WidgetMessageRequest, opts?: ApiFetchOptions) =>
    apiFetch<WidgetMessageResponse>(`/widget/session/${sessionId}/message`, {
      ...opts,
      method: "POST",
      body: payload,
    }),

  endSession: (sessionId: string, opts?: ApiFetchOptions) =>
    apiFetch<{ status: string; session_id: string }>(`/widget/session/${sessionId}/end`, {
      ...opts,
      method: "POST",
    }),
};
