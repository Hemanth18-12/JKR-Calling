"use client";

import { SignupRequest } from "@jkr/contracts";
import { ApiClientError, authApi } from "@jkr/sdk";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, FieldError, Input, Label } from "@jkr/ui";
import { zodResolver } from "@hookform/resolvers/zod";
import { ShieldCheck, Zap } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { useForm } from "react-hook-form";

export default function SignupPage() {
  const router = useRouter();
  const [formError, setFormError] = React.useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<SignupRequest>({ resolver: zodResolver(SignupRequest) });

  const onSubmit = async (data: SignupRequest) => {
    setFormError(null);
    try {
      await authApi.signup(data);
      window.location.href = "/app/dashboard";
    } catch (err) {
      setFormError(err instanceof ApiClientError ? err.message : "Something went wrong. Please try again.");
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
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-primary to-[#5B3FE4] shadow-lg shadow-primary/30">
            <Zap className="h-6 w-6 text-white" />
          </div>
          <div className="text-center">
            <h1 className="font-display text-xl font-bold text-foreground">JKR AI Calling</h1>
            <p className="text-sm text-muted-foreground">Create your workspace — it&apos;s free</p>
          </div>
        </div>

        <Card className="border-border/60 shadow-card-raised">
          <CardHeader className="pb-4">
            <CardTitle className="font-display text-lg font-semibold">Create your account</CardTitle>
            <CardDescription className="flex items-center gap-1.5">
              <ShieldCheck className="h-3.5 w-3.5 text-secondary" />
              No real call is ever placed until you explicitly enable it.
            </CardDescription>
          </CardHeader>
          <CardContent>
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
                Create account
              </Button>
            </form>
            <p className="mt-5 text-center text-sm text-muted-foreground">
              Already have an account?{" "}
              <Link href="/login" className="font-medium text-primary hover:underline">
                Log in
              </Link>
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
