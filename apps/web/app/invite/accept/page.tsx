"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { authApi, workspacesApi, ApiClientError } from "@jkr/sdk";
import type { InvitationDetailsPublic, UserOut } from "@jkr/contracts";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle } from "@jkr/ui";
import { Building2, CheckCircle2, AlertTriangle, LogOut, ArrowRight, Loader2, Zap } from "lucide-react";
import { signInWithGoogle, isFirebaseConfigured } from "@/lib/firebase";

function AcceptInvitationContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token");

  const [loading, setLoading] = useState(true);
  const [invitation, setInvitation] = useState<InvitationDetailsPublic | null>(null);
  const [currentUser, setCurrentUser] = useState<UserOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [accepting, setAccepting] = useState(false);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    if (!token) {
      setError("No invitation token found in this link. Please check your invitation email.");
      setLoading(false);
      return;
    }

    let isMounted = true;
    async function loadData() {
      try {
        const details = await workspacesApi.getInvitationDetails(token!);
        if (!isMounted) return;
        setInvitation(details);

        // Try getting current authenticated user
        try {
          const me = await authApi.me();
          if (isMounted) setCurrentUser(me.user);
        } catch {
          // Not logged in — will prompt user to log in
        }
      } catch (err: any) {
        if (!isMounted) return;
        setError(err instanceof ApiClientError ? err.message : "Invalid or expired invitation link.");
      } finally {
        if (isMounted) setLoading(false);
      }
    }

    loadData();
    return () => {
      isMounted = false;
    };
  }, [token]);

  const handleAccept = async () => {
    if (!token) return;
    setAccepting(true);
    setError(null);
    try {
      const res = await workspacesApi.acceptInvitation({ token });
      setSuccess(true);
      setTimeout(() => {
        window.location.href = "/app/dashboard";
      }, 1000);
    } catch (err: any) {
      setError(err instanceof ApiClientError ? err.message : "Failed to accept invitation.");
      setAccepting(false);
    }
  };

  const handleSwitchAccount = async () => {
    try {
      await authApi.logout();
      window.location.href = `/login?redirect=${encodeURIComponent(window.location.pathname + window.location.search)}`;
    } catch {
      window.location.href = "/login";
    }
  };

  const handleGoogleSignIn = async () => {
    try {
      if (!isFirebaseConfigured()) {
        window.location.href = `/login?redirect=${encodeURIComponent(window.location.pathname + window.location.search)}`;
        return;
      }
      const { idToken } = await signInWithGoogle();
      const user = await authApi.firebaseGoogleAuth({ id_token: idToken });
      if (user) {
        setCurrentUser(user);
        // Automatically accept after successful login
        const res = await workspacesApi.acceptInvitation({ token: token! });
        setSuccess(true);
        setTimeout(() => {
          window.location.href = "/app/dashboard";
        }, 1000);
      }
    } catch (err: any) {
      setError(err?.message || "Google authentication failed.");
    }
  };

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background px-4">
        <div className="flex flex-col items-center gap-3 text-center">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
          <p className="text-sm font-medium text-foreground">Validating invitation...</p>
        </div>
      </div>
    );
  }

  if (error || !invitation) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background px-4">
        <Card className="w-full max-w-md border-border/80 shadow-card-raised">
          <CardHeader className="text-center pb-2">
            <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-danger/10 text-danger">
              <AlertTriangle className="h-6 w-6" />
            </div>
            <CardTitle className="text-lg font-bold">Invitation Error</CardTitle>
            <CardDescription className="text-sm text-muted-foreground mt-1">
              {error || "Could not load invitation details."}
            </CardDescription>
          </CardHeader>
          <CardContent className="pt-4 text-center">
            <Button variant="outline" className="text-xs" onClick={() => router.push("/login")}>
              Go to Login
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  const isEmailMismatch = currentUser && currentUser.email.toLowerCase() !== invitation.email.toLowerCase();

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-background px-4">
      {/* Ambient background */}
      <div className="pointer-events-none absolute inset-0" aria-hidden="true">
        <div className="absolute left-1/4 top-0 h-96 w-96 -translate-x-1/2 rounded-full bg-primary/10 blur-[100px]" />
        <div className="absolute bottom-0 right-1/4 h-64 w-64 rounded-full bg-secondary/8 blur-[80px]" />
      </div>

      <div className="relative w-full max-w-md">
        {/* Brand header */}
        <div className="mb-6 flex flex-col items-center gap-2 text-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-primary to-[#FFA000] shadow-lg shadow-primary/30">
            <Zap className="h-6 w-6 text-black fill-black" />
          </div>
          <h1 className="font-display text-xl font-bold text-foreground">JKR AI Calling</h1>
        </div>

        <Card className="border-border/80 shadow-2xl bg-card overflow-hidden">
          <CardHeader className="text-center pb-4 border-b border-border/40">
            <div className="mx-auto mb-2 flex h-12 w-12 items-center justify-center rounded-xl bg-primary/10 border border-primary/20 text-primary">
              <Building2 className="h-6 w-6" />
            </div>
            <CardTitle className="text-xl font-bold">You&apos;re Invited!</CardTitle>
            <CardDescription className="text-sm text-muted-foreground mt-1">
              <strong>{invitation.inviter_name}</strong> invited you to join{" "}
              <strong className="text-foreground">{invitation.workspace_name}</strong>.
            </CardDescription>
          </CardHeader>

          <CardContent className="pt-6 space-y-5">
            {/* Invitation Details Summary */}
            <div className="rounded-xl border border-border/80 bg-surface-raised p-4 space-y-2.5 text-xs">
              <div className="flex justify-between items-center">
                <span className="text-muted-foreground font-medium">Workspace:</span>
                <span className="font-bold text-foreground">{invitation.workspace_name}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-muted-foreground font-medium">Assigned Role:</span>
                <span className="font-semibold text-primary">{invitation.role_name}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-muted-foreground font-medium">Invited Email:</span>
                <span className="font-mono text-foreground">{invitation.email}</span>
              </div>
            </div>

            {/* Email Mismatch Warning */}
            {isEmailMismatch && (
              <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 space-y-3 text-xs text-amber-200">
                <div className="flex items-start gap-2.5">
                  <AlertTriangle className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
                  <div>
                    <p className="font-semibold text-amber-300">Account Mismatch</p>
                    <p className="mt-1 leading-relaxed text-amber-200/90">
                      This invitation was addressed to <strong>{invitation.email}</strong>, but you are currently signed in as <strong>{currentUser.email}</strong>.
                    </p>
                  </div>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleSwitchAccount}
                  className="w-full text-xs font-semibold flex items-center justify-center gap-1.5 border-amber-500/40 text-amber-300 hover:bg-amber-500/20"
                >
                  <LogOut className="h-3.5 w-3.5" />
                  Sign Out & Switch to {invitation.email}
                </Button>
              </div>
            )}

            {/* Not Logged In Actions */}
            {!currentUser && (
              <div className="space-y-3 pt-2">
                <p className="text-xs text-center text-muted-foreground">
                  Sign in or create an account with <strong className="text-foreground">{invitation.email}</strong> to accept.
                </p>
                <Button
                  onClick={handleGoogleSignIn}
                  variant="outline"
                  className="w-full h-10 text-xs font-semibold flex items-center justify-center gap-2 border-border/80"
                >
                  <svg className="h-4 w-4" viewBox="0 0 24 24">
                    <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                    <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                    <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"/>
                    <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"/>
                  </svg>
                  Continue with Google
                </Button>
                <Button
                  onClick={() => {
                    const returnUrl = encodeURIComponent(window.location.pathname + window.location.search);
                    router.push(`/login?email=${encodeURIComponent(invitation.email)}&redirect=${returnUrl}`);
                  }}
                  className="w-full h-10 text-xs font-semibold"
                >
                  Sign in with Email OTP
                </Button>
              </div>
            )}

            {/* Logged in with matching email -> 1-click Accept */}
            {currentUser && !isEmailMismatch && (
              <div className="space-y-3 pt-2">
                {success ? (
                  <div className="flex items-center justify-center gap-2 text-emerald-400 py-3 text-sm font-semibold">
                    <CheckCircle2 className="h-5 w-5" />
                    <span>Accepted! Redirecting to workspace...</span>
                  </div>
                ) : (
                  <Button
                    onClick={handleAccept}
                    disabled={accepting}
                    className="w-full h-11 text-sm font-bold bg-primary text-black hover:bg-primary/90 flex items-center justify-center gap-2"
                  >
                    {accepting ? (
                      <>
                        <Loader2 className="h-4 w-4 animate-spin" />
                        <span>Accepting & Joining...</span>
                      </>
                    ) : (
                      <>
                        <span>Accept & Join {invitation.workspace_name}</span>
                        <ArrowRight className="h-4 w-4" />
                      </>
                    )}
                  </Button>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

export default function AcceptInvitationPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center bg-background px-4">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
        </div>
      }
    >
      <AcceptInvitationContent />
    </Suspense>
  );
}
