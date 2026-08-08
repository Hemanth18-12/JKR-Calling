"use client";

import { SignupRequest } from "@jkr/contracts";
import { ApiClientError, authApi } from "@jkr/sdk";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, FieldError, Input, Label } from "@jkr/ui";
import { zodResolver } from "@hookform/resolvers/zod";
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
      router.push("/app/dashboard");
      router.refresh();
    } catch (err) {
      setFormError(err instanceof ApiClientError ? err.message : "Something went wrong. Please try again.");
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>Create your account</CardTitle>
          <CardDescription>No real call is ever placed until you explicitly enable it.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div>
              <Label htmlFor="full_name">Full name</Label>
              <Input id="full_name" autoComplete="name" {...register("full_name")} />
              <FieldError>{errors.full_name?.message}</FieldError>
            </div>
            <div>
              <Label htmlFor="email">Email</Label>
              <Input id="email" type="email" autoComplete="email" {...register("email")} />
              <FieldError>{errors.email?.message}</FieldError>
            </div>
            <div>
              <Label htmlFor="password">Password</Label>
              <Input id="password" type="password" autoComplete="new-password" {...register("password")} />
              <FieldError>{errors.password?.message}</FieldError>
              <p className="mt-1 text-xs text-muted-foreground">At least 10 characters.</p>
            </div>
            {formError ? <p className="text-sm text-danger">{formError}</p> : null}
            <Button type="submit" className="w-full" loading={isSubmitting}>
              Create account
            </Button>
          </form>
          <p className="mt-4 text-center text-sm text-muted-foreground">
            Already have an account?{" "}
            <Link href="/login" className="text-primary hover:underline">
              Log in
            </Link>
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
