"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { authApi, ApiClientError } from "@jkr/sdk";
import { Zap, Loader2 } from "lucide-react";

function CallbackHandler() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    const code = searchParams.get("code");
    const error = searchParams.get("error");

    if (error || !code) {
      router.replace("/login?error=google_oauth_cancelled");
      return;
    }

    let isMounted = true;
    const processOAuth = async () => {
      try {
        await authApi.googleOAuthCallback({ code });
        if (isMounted) {
          window.location.href = "/app/dashboard";
        }
      } catch (err) {
        if (isMounted) {
          setErrorMessage(
            err instanceof ApiClientError ? err.message : "Google authentication failed. Please try again."
          );
        }
      }
    };

    processOAuth();

    return () => {
      isMounted = false;
    };
  }, [searchParams, router]);

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-background px-4">
      <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-primary to-[#FFA000] shadow-lg shadow-primary/30 mb-6">
        <Zap className="h-6 w-6 text-black fill-black" />
      </div>

      {errorMessage ? (
        <div className="max-w-md text-center space-y-4">
          <p className="text-sm text-danger font-medium">{errorMessage}</p>
          <button
            onClick={() => router.replace("/login")}
            className="text-xs font-semibold text-primary hover:underline"
          >
            &larr; Back to login
          </button>
        </div>
      ) : (
        <div className="flex flex-col items-center gap-3 text-center">
          <Loader2 className="h-6 w-6 animate-spin text-primary" />
          <p className="text-sm font-medium text-foreground">Completing Google authentication...</p>
          <p className="text-xs text-muted-foreground">Preparing your secure session</p>
        </div>
      )}
    </div>
  );
}

export default function GoogleOAuthCallbackPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen flex-col items-center justify-center bg-background px-4">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-primary to-[#FFA000] shadow-lg shadow-primary/30 mb-6">
            <Zap className="h-6 w-6 text-black fill-black" />
          </div>
          <div className="flex flex-col items-center gap-3 text-center">
            <Loader2 className="h-6 w-6 animate-spin text-primary" />
            <p className="text-sm font-medium text-foreground">Loading...</p>
          </div>
        </div>
      }
    >
      <CallbackHandler />
    </Suspense>
  );
}
