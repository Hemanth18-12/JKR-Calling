import { ApiClientError } from "@jkr/sdk";
import { authApi, workspacesApi } from "@jkr/sdk";
import { cookies } from "next/headers";

/**
 * Server-side session read. Next.js server-side `fetch` does not forward the
 * browser's cookies automatically — we have to read them from the incoming
 * request via `cookies()` and pass them along explicitly. See
 * packages/sdk/src/client.ts's module docstring for the cross-port cookie
 * note (this only works because browsers scope cookies by domain, not port,
 * so a cookie `services/api` sets on :8000 is still sent by the browser to
 * :3000 — a deliberate local-dev simplification, not a production posture).
 */
export async function getServerSession() {
  const cookieHeader = cookies().toString();
  if (!cookieHeader) return null;

  try {
    return await authApi.me({ cookieHeader });
  } catch (err) {
    if (err instanceof ApiClientError && (err.status === 401 || err.status === 403 || err.status === 503)) {
      return null;
    }
    console.error("Failed to read server session:", err);
    return null;
  }
}

/** Convenience for every /app/* page that needs "the workspace this request
 * is operating in": resolves the session and its active (or first) workspace
 * in one call, using a single cookie header forwarded to both requests. */
export async function getActiveWorkspaceContext() {
  const cookieHeader = cookies().toString();
  const me = await getServerSession();
  const workspaces = await workspacesApi.list({ cookieHeader }).catch(() => []);
  const workspace = workspaces.find((w) => w.id === me?.active_workspace_id) ?? workspaces[0] ?? null;
  return { me, workspaces, workspace, cookieHeader };
}
