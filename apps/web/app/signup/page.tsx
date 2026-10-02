"use client";

import { SignupRequest } from "@jkr/contracts";
import { ApiClientError, authApi } from "@jkr/sdk";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, FieldError, Input, Label } from "@jkr/ui";
import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowLeft, MailCheck, RefreshCw, ShieldCheck, Zap } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { useForm } from "react-hook-form";

export default function SignupPage() {
  const router = useRouter();
  const [step, setStep] = React.useState<"form" | "otp">("form");
  const [pendingEmail, setPendingEmail] = React.useState<string>("");
  const [otpCode, setOtpCode] = React.useState("");
  const [otpError, setOtpError] = React.useState<string | null>(null);
  const [otpVerifying, setOtpVerifying] = React.useState(false);
  const [resendCooldown, setResendCooldown] = React.useState(0);
  const [resending, setResending] = React.useState(false);

  const [formError, setFormError] = React.useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<SignupRequest>({ resolver: zodResolver(SignupRequest) });

  // Cooldown countdown timer
  React.useEffect(() => {
    if (resendCooldown <= 0) return;
    const timer = setInterval(() => {
      setResendCooldown((prev) => Math.max(0, prev - 1));
    }, 1000);
    return () => clearInterval(timer);
  }, [resendCooldown]);

  const [googleLoading, setGoogleLoading] = React.useState(false);

  React.useEffect(() => {
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      const err = params.get("error");
      if (err === "google_oauth_cancelled") {
        setFormError("Google sign-up was cancelled. Please try again or sign up with your email.");
      } else if (err === "google_auth_failed") {
        setFormError("Google authentication failed. Please try again.");
      }
    }
  }, []);

  const handleGoogleSignUp = async () => {
    setGoogleLoading(true);
    setFormError(null);
    try {
      const res = await authApi.getGoogleOAuthUrl();
      if (res.enabled && res.url) {
        window.location.href = res.url;
      } else {
        // Dev/demo fallback when live Google Cloud OAuth credentials are not set
        const user = await authApi.googleOAuthCallback({ code: "demo_google_user@jkr.ai" });
        if (user) {
          window.location.href = "/app/dashboard";
        }
      }
    } catch (err) {
      setFormError(err instanceof ApiClientError ? err.message : "Google authentication failed. Please try again.");
      setGoogleLoading(false);
    }
  };

  const onSubmit = async (data: SignupRequest) => {
    setFormError(null);
    try {
      const res = await authApi.signup(data);
      if ("status" in res && res.status === "otp_required") {
        setPendingEmail(data.email);
        setStep("otp");
        setResendCooldown(60);
        setOtpCode("");
        setOtpError(null);
      } else {
        // Direct creation (e.g. demo account)
        window.location.href = "/app/dashboard";
      }
    } catch (err) {
      setFormError(err instanceof ApiClientError ? err.message : "Something went wrong. Please try again.");
    }
  };

  const handleVerifyOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!otpCode || otpCode.trim().length !== 6) {
      setOtpError("Please enter the 6-digit code.");
      return;
    }
    setOtpError(null);
    setOtpVerifying(true);
    try {
      await authApi.verifyOtp({
        email: pendingEmail,
        purpose: "signup",
        code: otpCode.trim(),
      });
      window.location.href = "/app/dashboard";
    } catch (err) {
      setOtpError(err instanceof ApiClientError ? err.message : "Verification failed. Please check the code and try again.");
    } finally {
      setOtpVerifying(false);
    }
  };

  const handleResend = async () => {
    if (resendCooldown > 0 || resending) return;
    setResending(true);
    setOtpError(null);
    try {
      await authApi.resendOtp({ email: pendingEmail, purpose: "signup" });
      setResendCooldown(60);
    } catch (err) {
      setOtpError(err instanceof ApiClientError ? err.message : "Could not resend code. Please try again.");
    } finally {
      setResending(false);
    }
  };

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-background px-4">
      {/* Ambient background */}
      <div className="pointer-events-none absolute inset-0" aria-hidden="true">
        <div className="absolute right-1/4 top-0 h-96 w-96 rounded-full bg-primary/10 blur-[100px]" />
        <div className="absolute bottom-0 left-1/4 h-64 w-64 rounded-full bg-secondary/8 blur-[80px]" />
      </div>

      <div className="relative w-full max-w-sm">
        {/* Logo */}
        <div className="mb-8 flex flex-col items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-primary to-[#FFA000] shadow-lg shadow-primary/30">
            <Zap className="h-6 w-6 text-black fill-black" />
          </div>
          <div className="text-center">
            <h1 className="font-display text-xl font-bold text-foreground">JKR AI Calling</h1>
            <p className="text-sm text-muted-foreground">Create your workspace — it&apos;s free</p>
          </div>
        </div>

        <Card className="border-border/60 shadow-card-raised">
          {step === "form" ? (
            <>
              <CardHeader className="pb-4">
                <CardTitle className="font-display text-lg font-semibold">Create your account</CardTitle>
                <CardDescription className="flex items-center gap-1.5">
                  <ShieldCheck className="h-3.5 w-3.5 text-secondary" />
                  We will send a 6-digit verification code to your email.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Button
                  type="button"
                  variant="outline"
                  onClick={handleGoogleSignUp}
                  disabled={googleLoading}
                  className="w-full flex items-center justify-center gap-2.5 h-10 border-border/80 bg-background/50 hover:bg-muted font-medium text-foreground transition-all shadow-sm mb-4"
                >
                  <svg className="h-4 w-4" viewBox="0 0 24 24">
                    <path
                      fill="#4285F4"
                      d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                    />
                    <path
                      fill="#34A853"
                      d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                    />
                    <path
                      fill="#FBBC05"
                      d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"
                    />
                    <path
                      fill="#EA4335"
                      d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"
                    />
                  </svg>
                  <span>{googleLoading ? "Connecting to Google..." : "Continue with Google"}</span>
                </Button>

                <div className="relative my-4 flex items-center justify-center">
                  <div className="absolute inset-0 flex items-center">
                    <div className="w-full border-t border-border/60" />
                  </div>
                  <span className="relative bg-card px-2 text-xs uppercase text-muted-foreground font-medium">
                    Or continue with email
                  </span>
                </div>

                <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
                  <div>
                    <Label htmlFor="full_name">Full name</Label>
                    <Input id="full_name" autoComplete="name" className="mt-1.5" {...register("full_name")} />
                    <FieldError>{errors.full_name?.message}</FieldError>
                  </div>
                  <div>
                    <Label htmlFor="email">Email</Label>
                    <Input id="email" type="email" autoComplete="email" className="mt-1.5" {...register("email")} />
                    <FieldError>{errors.email?.message}</FieldError>
                  </div>
                  <div>
                    <Label htmlFor="password">Password</Label>
                    <Input
                      id="password"
                      type="password"
                      autoComplete="new-password"
                      className="mt-1.5"
                      {...register("password")}
                    />
                    <FieldError>{errors.password?.message}</FieldError>
                    <p className="mt-1.5 text-xs text-muted-foreground">At least 10 characters.</p>
                  </div>
                  {formError ? (
                    <div className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger">
                      {formError}
                    </div>
                  ) : null}
                  <Button type="submit" className="w-full" variant="gradient" loading={isSubmitting}>
                    Continue &amp; Send OTP
                  </Button>
                </form>
                <p className="mt-5 text-center text-sm text-muted-foreground">
                  Already have an account?{" "}
                  <Link href="/login" className="font-medium text-primary hover:underline">
                    Log in
                  </Link>
                </p>
              </CardContent>
            </>
          ) : (
            /* Step 2: 6-Digit OTP Verification Screen */
            <>
              <CardHeader className="pb-4">
                <div className="mb-2 flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 text-primary border border-primary/20">
                  <MailCheck className="h-5 w-5" />
                </div>
                <CardTitle className="font-display text-lg font-semibold">Verify your email</CardTitle>
                <CardDescription className="text-xs leading-relaxed">
                  We sent a 6-digit code to <strong className="text-foreground">{pendingEmail}</strong>.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <form onSubmit={handleVerifyOtp} className="space-y-4">
                  <div>
                    <Label htmlFor="otp">Enter 6-digit code</Label>
                    <Input
                      id="otp"
                      type="text"
                      inputMode="numeric"
                      pattern="[0-9]*"
                      maxLength={6}
                      autoFocus
                      placeholder="• • • • • •"
                      className="mt-1.5 text-center text-2xl tracking-[0.5em] font-mono font-bold h-12"
                      value={otpCode}
                      onChange={(e) => {
                        const val = e.target.value.replace(/\D/g, "").slice(0, 6);
                        setOtpCode(val);
                      }}
                    />
                    <p className="mt-1.5 text-xs text-muted-foreground text-center">Code expires in 10 minutes.</p>
                  </div>

                  {otpError ? (
                    <div className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger">
                      {otpError}
                    </div>
                  ) : null}

                  <Button
                    type="submit"
                    className="w-full"
                    variant="gradient"
                    loading={otpVerifying}
                    disabled={otpCode.length !== 6}
                  >
                    Verify &amp; Create Account
                  </Button>
                </form>

                <div className="mt-5 flex flex-col items-center gap-3 text-xs">
                  <button
                    type="button"
                    disabled={resendCooldown > 0 || resending}
                    onClick={handleResend}
                    className="flex items-center gap-1.5 text-primary hover:underline disabled:text-muted-foreground disabled:no-underline font-medium"
                  >
                    <RefreshCw className={`h-3 w-3 ${resending ? "animate-spin" : ""}`} />
                    {resendCooldown > 0 ? `Resend code in ${resendCooldown}s` : "Didn't receive code? Resend"}
                  </button>

                  <button
                    type="button"
                    onClick={() => {
                      setStep("form");
                      setOtpError(null);
                    }}
                    className="flex items-center gap-1 text-muted-foreground hover:text-foreground transition-colors"
                  >
                    <ArrowLeft className="h-3 w-3" /> Change email address
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
