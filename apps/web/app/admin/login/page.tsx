"use client";

import { ApiClientError, authApi } from "@jkr/sdk";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Input,
  Label,
} from "@jkr/ui";
import {
  ArrowLeft,
  KeyRound,
  Lock,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  User,
  Zap,
} from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { Suspense } from "react";

import { MotionOtpInput } from "@/components/motion-otp-input";

function AdminLoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [step, setStep] = React.useState<"login" | "otp">("login");
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [otpCode, setOtpCode] = React.useState("");

  const [error, setError] = React.useState<string | null>(null);
  const [submitting, setSubmitting] = React.useState(false);
  const [resendCooldown, setResendCooldown] = React.useState(0);
  const [resending, setResending] = React.useState(false);

  React.useEffect(() => {
    if (!searchParams.get("error")) {
      authApi
        .me()
        .then((res) => {
          if (res?.user) {
            window.location.href = "/admin";
          }
        })
        .catch(() => {
          // Not logged in, stay on login page
        });
    }
  }, [searchParams]);

  React.useEffect(() => {
    const errParam = searchParams.get("error");
    if (errParam === "forbidden") {
      setError(
        "Access Denied: Your account is not authorized to access the Admin Console. Please log in with an administrator account."
      );
    } else if (errParam === "unauthorized") {
      setError("Please log in with your administrator credentials to continue.");
    }
  }, [searchParams]);

  React.useEffect(() => {
    if (resendCooldown <= 0) return;
    const timer = setInterval(() => {
      setResendCooldown((prev) => Math.max(0, prev - 1));
    }, 1000);
    return () => clearInterval(timer);
  }, [resendCooldown]);

  const handleLoginSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    const cleanEmail = email.trim().toLowerCase();

    if (!cleanEmail) {
      setError("Please enter your administrator account email.");
      return;
    }

    if (!password) {
      setError("Please enter your administrator account password.");
      return;
    }

    setSubmitting(true);
    try {
      const res = await authApi.adminLogin({
        email: cleanEmail,
        password,
      });

      if ("status" in res && res.status === "otp_required") {
        setStep("otp");
        setResendCooldown(60);
        setOtpCode("");
      } else {
        // Direct session created
        window.location.href = "/admin";
      }
    } catch (err: any) {
      if (err instanceof ApiClientError && err.status === 403) {
        setError("Access Denied: You are not authorized to access this administration portal.");
      } else if (err instanceof ApiClientError && err.status === 401) {
        setError("Invalid email or password. Please verify your credentials.");
      } else {
        setError(err?.message || "Authentication failed. Please check your credentials.");
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handleVerifyOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!otpCode || otpCode.trim().length !== 6) {
      setError("Please enter the 6-digit verification code.");
      return;
    }

    setError(null);
    setSubmitting(true);
    try {
      await authApi.verifyOtp({
        email: email.trim().toLowerCase(),
        purpose: "login",
        code: otpCode.trim(),
      });
      window.location.href = "/admin";
    } catch (err: any) {
      setError(
        err instanceof ApiClientError
          ? err.message
          : "Invalid verification code. Please check your email and try again."
      );
    } finally {
      setSubmitting(false);
    }
  };

  const handleResendOtp = async () => {
    if (resendCooldown > 0 || resending) return;
    setResending(true);
    setError(null);
    try {
      await authApi.resendOtp({
        email: email.trim().toLowerCase(),
        purpose: "login",
      });
      setResendCooldown(60);
    } catch (err: any) {
      setError(err?.message || "Could not resend code. Please try again.");
    } finally {
      setResending(false);
    }
  };

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-background px-4">
      {/* Background glow */}
      <div className="pointer-events-none absolute inset-0" aria-hidden="true">
        <div className="absolute left-1/2 top-10 h-96 w-96 -translate-x-1/2 rounded-full bg-primary/10 blur-[120px]" />
      </div>

      <div className="relative w-full max-w-md space-y-6">
        {/* Header Badge */}
        <div className="flex flex-col items-center gap-3 text-center">
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-primary to-amber-600 shadow-xl shadow-primary/20 border border-primary/40">
            <ShieldCheck className="h-7 w-7 text-black stroke-[2.5]" />
          </div>
          <div>
            <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-primary/10 border border-primary/30 text-primary text-xs font-bold mb-2">
              <Lock className="h-3.5 w-3.5" />
              Restricted Platform Portal
            </div>
            <h1 className="text-2xl font-black text-foreground tracking-tight">
              JKR Admin Console
            </h1>
            <p className="text-xs text-muted-foreground mt-1 max-w-xs mx-auto">
              Gated administration portal. Authorized platform operators only.
            </p>
          </div>
        </div>

        <Card className="border-border/80 shadow-2xl bg-surface overflow-hidden">
          {/* Two-Option Toggle: User Login vs Admin Login */}
          <div className="p-3 pb-0">
            <div className="grid grid-cols-2 p-1 bg-surface-raised border border-border/80 rounded-xl text-xs font-semibold">
              <button
                type="button"
                onClick={() => router.push("/login")}
                className="py-2 rounded-lg text-muted-foreground hover:text-foreground transition-all flex items-center justify-center gap-1.5"
              >
                <User className="h-3.5 w-3.5" />
                User Login
              </button>
              <button
                type="button"
                className="py-2 rounded-lg bg-primary text-black font-bold shadow-sm flex items-center justify-center gap-1.5 transition-all"
              >
                <ShieldCheck className="h-3.5 w-3.5" />
                Admin Login
              </button>
            </div>
          </div>

          {step === "login" ? (
            <>
              <CardHeader className="pb-4 pt-3">
                <CardTitle className="text-base font-bold flex items-center justify-between">
                  <span>Administrator Authentication</span>
                  <Badge variant="outline" className="border-amber-500/30 text-amber-400 text-[10px]">
                    Super Admin
                  </Badge>
                </CardTitle>
                <CardDescription className="text-xs">
                  Enter your administrator credentials to access platform controls.
                </CardDescription>
              </CardHeader>

              <CardContent>
                <form onSubmit={handleLoginSubmit} className="space-y-4">
                  <div>
                    <Label htmlFor="admin-email" className="text-xs font-medium">
                      Admin Email
                    </Label>
                    <Input
                      id="admin-email"
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="admin@domain.com"
                      className="mt-1.5 text-xs font-medium"
                      required
                      autoFocus
                    />
                    <p className="text-[10px] text-muted-foreground mt-1">
                      Enter your authorized administrator email address.
                    </p>
                  </div>

                  <div>
                    <Label htmlFor="admin-password" className="text-xs font-medium">
                      Password
                    </Label>
                    <Input
                      id="admin-password"
                      type="password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="••••••••••••"
                      className="mt-1.5"
                      required
                    />
                  </div>

                  {error && (
                    <div className="rounded-xl border border-rose-500/40 bg-rose-500/10 p-3 text-xs text-rose-400 flex items-start gap-2">
                      <ShieldAlert className="h-4 w-4 shrink-0 mt-0.5" />
                      <span>{error}</span>
                    </div>
                  )}

                  <Button
                    type="submit"
                    variant="gradient"
                    className="w-full font-bold h-10 shadow-md"
                    loading={submitting}
                  >
                    Authenticate Administrator →
                  </Button>
                </form>

                <div className="mt-5 border-t border-border/60 pt-4 text-center">
                  <Link
                    href="/login"
                    className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
                  >
                    <ArrowLeft className="h-3.5 w-3.5" /> Return to Regular User Login
                  </Link>
                </div>
              </CardContent>
            </>
          ) : (
            /* OTP step */
            <>
              <CardHeader className="pb-4 pt-3">
                <div className="mb-2 flex h-10 w-10 items-center justify-center rounded-xl bg-amber-500/10 text-amber-400 border border-amber-500/20">
                  <KeyRound className="h-5 w-5" />
                </div>
                <CardTitle className="text-base font-bold">Admin Two-Factor Verification</CardTitle>
                <CardDescription className="text-xs leading-relaxed">
                  A 6-digit security code has been sent to your administrator email address.
                </CardDescription>
              </CardHeader>

              <CardContent>
                <form onSubmit={handleVerifyOtp} className="space-y-4">
                  <div>
                    <Label className="text-xs font-semibold text-muted-foreground block text-center mb-3">
                      Enter 6-digit Code
                    </Label>
                    <MotionOtpInput
                      id="admin-otp"
                      value={otpCode}
                      onChange={(val) => {
                        setOtpCode(val);
                        setError(null);
                      }}
                      hasError={Boolean(error)}
                      disabled={submitting}
                    />
                    <p className="mt-2 text-[11px] text-muted-foreground text-center">
                      Code valid for 10 minutes.
                    </p>
                  </div>

                  {error && (
                    <div className="rounded-xl border border-rose-500/40 bg-rose-500/10 p-3 text-xs text-rose-400 flex items-start gap-2">
                      <ShieldAlert className="h-4 w-4 shrink-0 mt-0.5" />
                      <span>{error}</span>
                    </div>
                  )}

                  <Button
                    type="submit"
                    variant="gradient"
                    className="w-full font-bold h-10 shadow-md"
                    loading={submitting}
                    disabled={otpCode.length !== 6}
                  >
                    Verify &amp; Enter Admin Dashboard
                  </Button>
                </form>

                <div className="mt-5 flex flex-col items-center gap-3 text-xs">
                  <button
                    type="button"
                    disabled={resendCooldown > 0 || resending}
                    onClick={handleResendOtp}
                    className="flex items-center gap-1.5 text-primary hover:underline disabled:text-muted-foreground disabled:no-underline font-medium"
                  >
                    <RefreshCw className={`h-3 w-3 ${resending ? "animate-spin" : ""}`} />
                    {resendCooldown > 0
                      ? `Resend code in ${resendCooldown}s`
                      : "Didn't receive code? Resend"}
                  </button>

                  <button
                    type="button"
                    onClick={() => {
                      setStep("login");
                      setError(null);
                    }}
                    className="flex items-center gap-1 text-muted-foreground hover:text-foreground transition-colors"
                  >
                    <ArrowLeft className="h-3 w-3" /> Back to admin login
                  </button>
                </div>
              </CardContent>
            </>
          )}
        </Card>
      </div>
    </div>
  );
}

export default function AdminLoginPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center bg-background">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-primary border-t-transparent" />
        </div>
      }
    >
      <AdminLoginForm />
    </Suspense>
  );
}
