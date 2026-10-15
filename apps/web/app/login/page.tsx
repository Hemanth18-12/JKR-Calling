"use client";

import { LoginRequest } from "@jkr/contracts";
import { ApiClientError, authApi } from "@jkr/sdk";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, FieldError, Input, PasswordInput, Label } from "@jkr/ui";
import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowLeft, CheckCircle2, KeyRound, Loader2, RefreshCw, ShieldCheck, User, Zap, Clock, AlertCircle, Mail } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { useForm } from "react-hook-form";

import {
  signInWithGoogle,
  signInWithGoogleRedirect,
  checkRedirectResult,
  isFirebaseConfigured,
  getFirebaseAuth,
} from "@/lib/firebase";

export default function LoginPage() {
  const router = useRouter();
  const [step, setStep] = React.useState<"form" | "otp">("form");
  const [loginMode, setLoginMode] = React.useState<"password" | "otp_only">("password");
  const [pendingEmail, setPendingEmail] = React.useState<string>("");
  const [otpCode, setOtpCode] = React.useState("");
  const [otpError, setOtpError] = React.useState<string | null>(null);
  const [otpVerifying, setOtpVerifying] = React.useState(false);
  const [resendCooldown, setResendCooldown] = React.useState(0);
  const [resending, setResending] = React.useState(false);
  const [otpRequestLoading, setOtpRequestLoading] = React.useState(false);

  const [formError, setFormError] = React.useState<string | null>(null);
  const [popupBlocked, setPopupBlocked] = React.useState(false);
  const {
    register,
    handleSubmit,
    setValue,
    getValues,
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

  // Google Login state
  const [googleLoading, setGoogleLoading] = React.useState(false);
  const [googleSuccess, setGoogleSuccess] = React.useState(false);
  const [stepLabel, setStepLabel] = React.useState("Opening Google...");
  const [isOverTime, setIsOverTime] = React.useState(false);
  const timerIntervalRef = React.useRef<ReturnType<typeof setInterval> | null>(null);

  // Status progression during Google authentication (without numeric countdown)
  React.useEffect(() => {
    if (googleLoading) {
      setIsOverTime(false);
      setStepLabel("Opening Google...");
      let elapsedSeconds = 0;
      timerIntervalRef.current = setInterval(() => {
        elapsedSeconds += 1;
        if (elapsedSeconds >= 15) {
          setIsOverTime(true);
          setStepLabel("Almost there...");
        } else if (elapsedSeconds >= 8) {
          setStepLabel("Setting up your workspace...");
        } else if (elapsedSeconds >= 4) {
          setStepLabel("Verifying your account...");
        } else if (elapsedSeconds >= 2) {
          setStepLabel("Connecting to Google...");
        }
      }, 1000);
    } else {
      if (timerIntervalRef.current) {
        clearInterval(timerIntervalRef.current);
        timerIntervalRef.current = null;
      }
    }
    return () => {
      if (timerIntervalRef.current) {
        clearInterval(timerIntervalRef.current);
      }
    };
  }, [googleLoading]);

  React.useEffect(() => {
    if (typeof window !== "undefined") {
      // Pre-warm Firebase Auth and backend routes so everything is instantaneous on click
      try {
        getFirebaseAuth();
      } catch {}
      fetch("/health", { keepalive: true }).catch(() => {});
      fetch("/api/v1/health", { keepalive: true }).catch(() => {});
      fetch("/api/v1/auth/oauth/google/url").catch(() => {});

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

      // Check Firebase redirect result if arriving back from mobile or full-page redirect
      if (isFirebaseConfigured()) {
        checkRedirectResult()
          .then(async (res) => {
            if (res?.idToken) {
              setGoogleLoading(true);
              setStepLabel("Authenticating session with server...");
              const user = await authApi.googleAuth({ id_token: res.idToken });
              if (user) {
                setGoogleSuccess(true);
                setStepLabel("Success! Opening workspace...");
                setTimeout(() => {
                  window.location.href = getRedirectTarget();
                }, 300);
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
    setGoogleSuccess(false);
    setIsOverTime(false);
    setFormError(null);
    setPopupBlocked(false);

    try {
      const { idToken } = await signInWithGoogle();
      if (!idToken) {
        setGoogleLoading(false);
        return;
      }

      setStepLabel("Verifying session with server...");

      const user = await authApi.googleAuth({ id_token: idToken });

      if (user) {
        setGoogleSuccess(true);
        setStepLabel("Verified! Opening workspace...");
        setTimeout(() => {
          window.location.href = getRedirectTarget();
        }, 300);
      }
    } catch (err: any) {
      setGoogleSuccess(false);
      setGoogleLoading(false);
      if (err?.code === "auth/popup-closed-by-user") {
        // User closed the popup - clean dismiss without scary error
        setFormError(null);
      } else if (err?.code === "auth/cancelled-popup-request") {
        // Ignored duplicate
      } else if (err?.code === "auth/unauthorized-domain") {
        const host = typeof window !== "undefined" ? window.location.hostname : "this domain";
        setFormError(
          `Domain "${host}" is not authorized in Firebase. Add "${host}" to Firebase Console > Authentication > Settings > Authorized Domains.`
        );
      } else if (err?.code === "auth/popup-blocked") {
        setPopupBlocked(true);
        setFormError(
          "The Google sign-in pop-up was blocked by your browser. Click 'Open Google Sign-In' below to proceed."
        );
      } else if (err?.code === "auth/network-request-failed") {
        setFormError("Network error connecting to Google. Please check your internet connection.");
      } else {
        const rawMsg = err instanceof ApiClientError ? err.message : (err?.message || "");
        if (rawMsg.includes("QueuePool") || rawMsg.includes("timeout") || rawMsg.includes("timed out")) {
          setFormError("Server is experiencing high traffic. Please try again or use Email login below.");
        } else {
          setFormError(rawMsg || "Google authentication could not be completed. Please try again.");
        }
      }
    } finally {
      if (!googleSuccess) {
        setGoogleLoading(false);
      }
    }
  };

  const handleGoogleRedirectSignIn = async () => {
    try {
      setGoogleLoading(true);
      setStepLabel("Redirecting to Google...");
      await signInWithGoogleRedirect();
    } catch (err: any) {
      setGoogleLoading(false);
      setFormError(err?.message || "Could not redirect to Google. Please check your browser settings.");
    }
  };

  const handleRequestOtpLogin = async () => {
    const email = getValues("email")?.trim();
    if (!email || !email.includes("@")) {
      setFormError("Please enter a valid email address first.");
      return;
    }
    setFormError(null);
    setOtpRequestLoading(true);
    try {
      const res = await authApi.requestOtp({ email });
      setPendingEmail(email);
      setStep("otp");
      setResendCooldown(60);
      setOtpCode("");
      setOtpError(null);
    } catch (err: any) {
      setFormError(err instanceof ApiClientError ? err.message : "Could not send verification code. Please check your email and try again.");
    } finally {
      setOtpRequestLoading(false);
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
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-background px-4">
      {/* Subtle background grid pattern */}
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(#ffffff08_1px,transparent_1px)] [background-size:24px_24px]" aria-hidden="true" />

      <div className="relative w-full max-w-sm">
        {/* Logo Header */}
        <div className="mb-6 flex flex-col items-center gap-2.5">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary text-black font-bold shadow-sm">
            <Zap className="h-5 w-5 fill-black" />
          </div>
          <div className="text-center">
            <h1 className="font-display text-xl font-bold tracking-tight text-foreground">JKR AI Calling</h1>
            <p className="text-xs text-muted-foreground mt-0.5">India-first AI voice platform</p>
          </div>
        </div>

        {/* Clean Surface Card */}
        <Card className="relative border-border/80 bg-surface shadow-sm overflow-hidden">
          {/* Specular glare reflection moving in 3D */}
          <div
            className="pointer-events-none absolute inset-0 z-20 transition-opacity duration-200"
            style={{
              opacity: tilt.active ? 0.35 : 0,
              background: `radial-gradient(circle at ${tilt.glareX}% ${tilt.glareY}%, rgba(255, 212, 0, 0.25) 0%, transparent 60%)`,
            }}
            aria-hidden="true"
          />

          {/* Smooth full-card overlay on successful login navigation */}
          {googleSuccess && (
            <div className="absolute inset-0 z-30 flex flex-col items-center justify-center bg-background/95 backdrop-blur-sm p-6 text-center animate-in fade-in duration-200">
              <Loader2 className="h-7 w-7 animate-spin text-primary mb-3" />
              <p className="font-semibold text-foreground text-sm">Signed In Successfully</p>
              <p className="text-xs text-muted-foreground mt-1">Opening your workspace...</p>
            </div>
          )}

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
                {/* Smooth Progress Notification when signing in */}
                {googleLoading && (
                  <div className="mb-4 rounded-xl border border-primary/30 bg-primary/5 p-4 shadow-sm animate-in fade-in duration-200">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <Loader2 className="h-4 w-4 animate-spin text-primary" />
                        <span className="text-xs font-semibold text-foreground">Signing you in…</span>
                      </div>
                      <span className="text-[11px] text-muted-foreground font-medium">Please wait</span>
                    </div>

                    {/* Smooth dynamic progress bar without numeric countdown */}
                    <div className="w-full bg-border/60 h-1.5 rounded-full overflow-hidden mb-2.5 relative">
                      <div className="bg-primary h-full rounded-full animate-pulse transition-all duration-500 w-full" />
                    </div>

                    <div className="flex items-center justify-between text-xs text-muted-foreground">
                      <span className="font-medium text-foreground">{stepLabel}</span>
                    </div>

                    {isOverTime && (
                      <div className="mt-3 pt-3 border-t border-border/80 text-xs animate-in fade-in">
                        <p className="text-muted-foreground mb-2">
                          Signing in is taking longer than usual.
                        </p>
                        <div className="flex items-center gap-2">
                          <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            onClick={handleGoogleSignIn}
                            className="h-8 text-xs font-medium"
                          >
                            <RefreshCw className="h-3 w-3 mr-1" />
                            Try again
                          </Button>
                          <Button
                            type="button"
                            size="sm"
                            variant="secondary"
                            onClick={() => {
                              setGoogleLoading(false);
                              setIsOverTime(false);
                            }}
                            className="h-8 text-xs font-medium"
                          >
                            Cancel
                          </Button>
                        </div>
                      </div>
                    )}
                  </div>
                )}

                <Button
                  type="button"
                  variant="outline"
                  onClick={handleGoogleSignIn}
                  disabled={googleLoading || googleSuccess}
                  className="w-full flex items-center justify-center gap-2.5 h-10 border-border/80 bg-background/50 hover:bg-muted font-medium text-foreground transition-all shadow-sm mb-4"
                >
                  {googleSuccess ? (
                    <CheckCircle2 className="h-4 w-4 text-emerald-500 animate-in fade-in" />
                  ) : googleLoading ? (
                    <Loader2 className="h-4 w-4 animate-spin text-primary" />
                  ) : (
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
                  )}
                  <span className="text-xs sm:text-sm font-medium">
                    {googleLoading ? stepLabel : "Continue with Google"}
                  </span>
                </Button>

                {popupBlocked && (
                  <Button
                    type="button"
                    variant="gradient"
                    onClick={handleGoogleRedirectSignIn}
                    className="w-full font-bold shadow-md mb-4 animate-in fade-in"
                  >
                    Open Google Sign-In (Full Page)
                  </Button>
                )}

                <div className="relative my-4 flex items-center justify-center">
                  <div className="absolute inset-0 flex items-center">
                    <div className="w-full border-t border-border/60" />
                  </div>
                  <span className="relative bg-card px-2 text-xs uppercase text-muted-foreground font-medium">
                    Or continue with email
                  </span>
                </div>

                {loginMode === "password" ? (
                  <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
                    <div>
                      <Label htmlFor="email">Email</Label>
                      <Input id="email" type="email" autoComplete="email" className="mt-1.5" {...register("email")} />
                      <FieldError>{errors.email?.message}</FieldError>
                    </div>
                    <div>
                      <div className="flex items-center justify-between">
                        <Label htmlFor="password">Password</Label>
                        <button
                          type="button"
                          onClick={() => {
                            setFormError(null);
                            setLoginMode("otp_only");
                          }}
                          className="text-xs text-primary hover:underline font-medium"
                        >
                          Email OTP instead
                        </button>
                      </div>
                      <PasswordInput
                        id="password"
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
                    <Button type="submit" className="w-full font-bold shadow-md" variant="gradient" loading={isSubmitting} disabled={googleLoading}>
                      Sign In
                    </Button>
                  </form>
                ) : (
                  <div className="space-y-4">
                    <div>
                      <Label htmlFor="email-otp-input">Work Email</Label>
                      <Input
                        id="email-otp-input"
                        type="email"
                        autoComplete="email"
                        placeholder="you@company.com"
                        className="mt-1.5"
                        {...register("email")}
                      />
                      <FieldError>{errors.email?.message}</FieldError>
                      <p className="mt-1.5 text-xs text-muted-foreground">
                        We&apos;ll send a 6-digit login verification code. No password required.
                      </p>
                    </div>

                    {formError ? (
                      <div className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger animate-in fade-in">
                        {formError}
                      </div>
                    ) : null}

                    <Button
                      type="button"
                      onClick={handleRequestOtpLogin}
                      className="w-full font-bold shadow-md"
                      variant="gradient"
                      loading={otpRequestLoading}
                      disabled={googleLoading}
                    >
                      <Mail className="h-4 w-4 mr-1.5" />
                      Send 6-Digit Login Code
                    </Button>

                    <div className="text-center pt-1">
                      <button
                        type="button"
                        onClick={() => {
                          setFormError(null);
                          setLoginMode("password");
                        }}
                        className="text-xs text-muted-foreground hover:text-foreground underline transition-colors"
                      >
                        Use password instead
                      </button>
                    </div>
                  </div>
                )}
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
