"use client";

import { LoginRequest } from "@jkr/contracts";
import { ApiClientError, authApi } from "@jkr/sdk";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, FieldError, Input, Label } from "@jkr/ui";
import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowLeft, KeyRound, RefreshCw, ShieldCheck, User, Zap } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { useForm } from "react-hook-form";

import { signInWithGoogle, checkRedirectResult, isFirebaseConfigured } from "@/lib/firebase";

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
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<LoginRequest>({ resolver: zodResolver(LoginRequest) });

  const getRedirectTarget = React.useCallback(() => {
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      const redirect = params.get("redirect");
      if (redirect && redirect.startsWith("/")) {
        return redirect;
      }
    }
    return "/app/dashboard";
  }, []);

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
      const emailParam = params.get("email");
      if (emailParam) {
        setValue("email", emailParam);
      }
      const err = params.get("error");
      if (err === "google_oauth_cancelled") {
        setFormError("Google sign-in was cancelled. Please try again or log in with your email.");
      } else if (err === "google_auth_failed") {
        setFormError("Google authentication failed. Please check your credentials and try again.");
      }

      // Check Firebase redirect result if arriving back from mobile redirect
      if (isFirebaseConfigured()) {
        checkRedirectResult()
          .then(async (res) => {
            if (res?.idToken) {
              setGoogleLoading(true);
              const user = await authApi.firebaseGoogleAuth({ id_token: res.idToken });
              if (user) {
                window.location.href = getRedirectTarget();
              }
            }
          })
          .catch((error) => {
            setFormError(error?.message || "Google redirect authentication failed.");
          });
      }
    }
  }, [setValue, getRedirectTarget]);

  const handleGoogleSignIn = async () => {
    setGoogleLoading(true);
    setFormError(null);
    try {
      if (!isFirebaseConfigured()) {
        const redirectUri = window.location.origin + "/auth/oauth/google/callback";
        const res = await authApi.getGoogleOAuthUrl({ redirect_uri: redirectUri });
        if (res.enabled && res.url) {
          window.location.href = res.url;
          return;
        }
        setFormError(
          "Google sign-in is not configured yet. Please configure Firebase environment variables or use email login."
        );
        setGoogleLoading(false);
        return;
      }

      const { idToken } = await signInWithGoogle();
      if (!idToken) return;

      const user = await authApi.firebaseGoogleAuth({ id_token: idToken });
      if (user) {
        window.location.href = getRedirectTarget();
      }
    } catch (err: any) {
      if (err?.code === "auth/popup-closed-by-user") {
        setFormError("Google sign-in was cancelled (popup closed).");
      } else if (err?.code === "auth/cancelled-popup-request") {
        // Ignored duplicate
      } else if (err?.code === "auth/network-request-failed") {
        setFormError("Network error connecting to Google. Please check your connection.");
      } else {
        setFormError(
          err instanceof ApiClientError
            ? err.message
            : (err?.message || "Google authentication failed. Please try again.")
        );
      }
    } finally {
      setGoogleLoading(false);
    }
  };

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
        window.location.href = getRedirectTarget();
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
      window.location.href = getRedirectTarget();
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

  // 3D Card tilt physics
  const cardRef = React.useRef<HTMLDivElement>(null);
  const [tilt, setTilt] = React.useState({ x: 0, y: 0, glareX: 50, glareY: 50, active: false });

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!cardRef.current) return;
    const rect = cardRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const centerX = rect.width / 2;
    const centerY = rect.height / 2;
    const rotateX = ((y - centerY) / centerY) * -6;
    const rotateY = ((x - centerX) / centerX) * 6;
    const glareX = (x / rect.width) * 100;
    const glareY = (y / rect.height) * 100;
    setTilt({ x: rotateX, y: rotateY, glareX, glareY, active: true });
  };

  const handleMouseLeave = () => {
    setTilt({ x: 0, y: 0, glareX: 50, glareY: 50, active: false });
  };

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-background px-4 perspective-1000">
      {/* 3D Ambient background lighting */}
      <div className="pointer-events-none absolute inset-0" aria-hidden="true">
        <div className="absolute left-1/4 top-0 h-96 w-96 -translate-x-1/2 rounded-full bg-primary/10 blur-[120px] animate-ambient-glow" />
        <div className="absolute bottom-0 right-1/4 h-80 w-80 rounded-full bg-secondary/8 blur-[100px]" />
        <div className="absolute inset-0 bg-[radial-gradient(#ffffff05_1px,transparent_1px)] [background-size:24px_24px]" />
      </div>

      <div
        ref={cardRef}
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
        className={`relative w-full max-w-sm preserve-3d transition-transform duration-200 ease-out ${!tilt.active ? "animate-float-3d" : ""}`}
        style={{
          transform: tilt.active
            ? `perspective(1000px) rotateX(${tilt.x}deg) rotateY(${tilt.y}deg) scale3d(1.02, 1.02, 1.02)`
            : undefined,
        }}
      >
        {/* Logo Header */}
        <div className="mb-6 flex flex-col items-center gap-2.5 preserve-3d" style={{ transform: "translateZ(20px)" }}>
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-primary to-[#FFA000] shadow-lg shadow-primary/30 transition-transform duration-300 hover:scale-110">
            <Zap className="h-6 w-6 text-black fill-black" />
          </div>
          <div className="text-center">
            <h1 className="font-display text-xl font-bold tracking-tight text-foreground">JKR AI Calling</h1>
            <p className="text-xs text-muted-foreground mt-0.5">India-first AI voice platform</p>
          </div>
        </div>

        {/* 3D Glass Surface Card */}
        <Card className="relative border-border/60 bg-surface/90 shadow-card-raised backdrop-blur-xl overflow-hidden card-3d transition-all duration-300 hover:border-primary/50 hover:shadow-2xl">
          {/* Specular glare reflection moving in 3D */}
          <div
            className="pointer-events-none absolute inset-0 z-20 transition-opacity duration-200"
            style={{
              opacity: tilt.active ? 0.35 : 0,
              background: `radial-gradient(circle at ${tilt.glareX}% ${tilt.glareY}%, rgba(255, 212, 0, 0.25) 0%, transparent 60%)`,
            }}
            aria-hidden="true"
          />

          {/* Two-Option Toggle: User Login vs Admin Login */}
          <div className="p-3 pb-0 relative z-10">
            <div className="grid grid-cols-2 p-1 bg-surface-raised border border-border/80 rounded-xl text-xs font-semibold">
              <button
                type="button"
                className="py-2 rounded-lg bg-primary text-black font-bold shadow-sm flex items-center justify-center gap-1.5 transition-all"
              >
                <User className="h-3.5 w-3.5" />
                User Login
              </button>
              <button
                type="button"
                onClick={() => router.push("/admin/login")}
                className="py-2 rounded-lg text-muted-foreground hover:text-foreground transition-all flex items-center justify-center gap-1.5"
              >
                <ShieldCheck className="h-3.5 w-3.5" />
                Admin Login
              </button>
            </div>
          </div>

          {step === "form" ? (
            <>
              <CardHeader className="pb-4 pt-3 relative z-10">
                <CardTitle className="font-display text-lg font-semibold">User Login</CardTitle>
                <CardDescription>Welcome back to your workspace.</CardDescription>
              </CardHeader>
              <CardContent>
                <Button
                  type="button"
                  variant="outline"
                  onClick={handleGoogleSignIn}
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
                    <div className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger animate-in fade-in">
                      {formError}
                    </div>
                  ) : null}
                  <Button type="submit" className="w-full font-bold shadow-md" variant="gradient" loading={isSubmitting}>
                    Continue &amp; Send OTP
                  </Button>
                </form>
                <p className="mt-5 text-center text-sm text-muted-foreground">
                  No account?{" "}
                  <Link href="/signup" className="font-semibold text-primary hover:underline">
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
                    <div className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger animate-in fade-in">
                      {otpError}
                    </div>
                  ) : null}

                  <Button
                    type="submit"
                    className="w-full font-bold shadow-md"
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
