/**
 * Hand-written typed fetch client (docs/DECISIONS/0001-tooling-and-monorepo.md
 * explains why this isn't a generated OpenAPI client for this pass). Works in
 * both Client Components (browser cookies via `credentials: "include"`) and
 * Server Components/Route Handlers (must forward the incoming `cookie`
 * header explicitly — Next.js server-side `fetch` does not do this for you).
 */

export class ApiClientError extends Error {
  constructor(
    public status: number,
    public code: number,
    message: string,
    public details: Record<string, unknown> = {}
  ) {
    super(message);
    this.name = "ApiClientError";
  }
}

export interface ApiFetchOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  cookieHeader?: string;
}

function resolveBaseUrl(): string {
  if (typeof window !== "undefined") {
    return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
  }
  return process.env.API_BASE_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
}

/** For call sites that need a raw URL rather than a fetch call — e.g. an
 * `EventSource` for `GET /calls/{id}/events` (docs/DECISIONS/0005), which
 * can't be built on top of `apiFetch`'s Response-based abstraction. */
export function apiBaseUrl(): string {
  return resolveBaseUrl();
}

export async function apiFetch<T>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  const { body, cookieHeader, headers, ...rest } = options;
  const base = resolveBaseUrl();

  const response = await fetch(`${base}/api/v1${path}`, {
    ...rest,
    method: options.method ?? (body ? "POST" : "GET"),
    credentials: "include",
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      ...(cookieHeader ? { cookie: cookieHeader } : {}),
      ...headers,
    },
    body: body ? JSON.stringify(body) : undefined,
  });

  const isJson = response.headers.get("content-type")?.includes("application/json");
  const payload = isJson ? await response.json().catch(() => null) : null;

  if (!response.ok) {
    const err = payload?.error;
    throw new ApiClientError(
      response.status,
      err?.code ?? response.status,
      err?.message ?? response.statusText ?? "Request failed",
      err?.details ?? {}
    );
  }

  return payload as T;
}
