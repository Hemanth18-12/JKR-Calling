"use client";

import { LoginRequest } from "@jkr/contracts";
import { ApiClientError, authApi } from "@jkr/sdk";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, FieldError, Input, Label } from "@jkr/ui";
import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowLeft, KeyRound, RefreshCw, Zap } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { useForm } from "react-hook-form";

export default function LoginPage() {
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
  } = useForm<LoginRequest>({ resolver: zodResolver(LoginRequest) });

  // Cooldown countdown timer
  React.useEffect(() => {
    if (resendCooldown <= 0) return;
    const timer = setInterval(() => {
      setResendCooldown((prev) => Math.max(0, prev - 1));
    }, 1000);
    return () => clearInterval(timer);
  }, [resendCooldown]);

  const onSubmit = async (data: LoginRequest) => {
    setFormError(null);
    try {
      const res = await authApi.login(data);
      if ("status" in res && res.status === "otp_required") {
        setPendingEmail(data.email);
        setStep("otp");
        setResendCooldown(60);
        setOtpCode("");
        setOtpError(null);
      } else {
        // Direct login (e.g. demo account)
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
        purpose: "login",
        code: otpCode.trim(),
      });
      window.location.href = "/app/dashboard";
    } catch (err) {
      setOtpError(err instanceof ApiClientError ? err.message : "Invalid code. Please check your email and try again.");
    } finally {
      setOtpVerifying(false);
    }
  };

  const handleResend = async () => {
    if (resendCooldown > 0 || resending) return;
    setResending(true);
    setOtpError(null);
    try {
      await authApi.resendOtp({ email: pendingEmail, purpose: "login" });
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
        <div className="absolute left-1/4 top-0 h-96 w-96 -translate-x-1/2 rounded-full bg-primary/10 blur-[100px]" />
        <div className="absolute bottom-0 right-1/4 h-64 w-64 rounded-full bg-secondary/8 blur-[80px]" />
      </div>

      <div className="relative w-full max-w-sm">
        {/* Logo */}
        <div className="mb-8 flex flex-col items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-primary to-[#FFA000] shadow-lg shadow-primary/30">
            <Zap className="h-6 w-6 text-black fill-black" />
          </div>
          <div className="text-center">
            <h1 className="font-display text-xl font-bold text-foreground">JKR AI Calling</h1>
            <p className="text-sm text-muted-foreground">India-first AI voice platform</p>
          </div>
        </div>

        <Card className="border-border/60 shadow-card-raised">
          {step === "form" ? (
            <>
              <CardHeader className="pb-4">
                <CardTitle className="font-display text-lg font-semibold">Log in</CardTitle>
                <CardDescription>Welcome back to your workspace.</CardDescription>
              </CardHeader>
              <CardContent>
                <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
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
                      autoComplete="current-password"
                      className="mt-1.5"
                      {...register("password")}
                    />
                    <FieldError>{errors.password?.message}</FieldError>
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
                  No account?{" "}
                  <Link href="/signup" className="font-medium text-primary hover:underline">
                    Sign up
                  </Link>
                </p>
              </CardContent>
            </>
          ) : (
            /* Step 2: 6-Digit OTP Verification Screen for Login */
            <>
              <CardHeader className="pb-4">
                <div className="mb-2 flex h-10 w-10 items-center justify-center rounded-xl bg-amber-500/10 text-amber-400 border border-amber-500/20">
                  <KeyRound className="h-5 w-5" />
                </div>
                <CardTitle className="font-display text-lg font-semibold">Two-Factor Authentication</CardTitle>
                <CardDescription className="text-xs leading-relaxed">
                  We sent a 6-digit login verification code to <strong className="text-foreground">{pendingEmail}</strong>.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <form onSubmit={handleVerifyOtp} className="space-y-4">
                  <div>
                    <Label htmlFor="login-otp">Enter 6-digit code</Label>
                    <Input
                      id="login-otp"
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
                    Verify &amp; Log In
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
                    <ArrowLeft className="h-3 w-3" /> Back to log in
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
