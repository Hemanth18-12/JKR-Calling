"use client";

import { WorkspaceCreate } from "@jkr/contracts";
import { ApiClientError, workspacesApi } from "@jkr/sdk";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, FieldError, Input, Label } from "@jkr/ui";
import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import * as React from "react";
import { useForm } from "react-hook-form";

function slugify(value: string) {
  return value
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "");
}

export function CreateWorkspaceForm() {
  const router = useRouter();
  const [formError, setFormError] = React.useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setValue,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<WorkspaceCreate>({
    resolver: zodResolver(WorkspaceCreate),
    defaultValues: { timezone: "Asia/Kolkata", default_language: "te-en-IN" },
  });
  const name = watch("name");

  React.useEffect(() => {
    if (name) setValue("slug", slugify(name), { shouldValidate: true });
  }, [name, setValue]);

  const onSubmit = async (data: WorkspaceCreate) => {
    setFormError(null);
    try {
      await workspacesApi.create(data);
      router.refresh();
    } catch (err) {
      setFormError(err instanceof ApiClientError ? err.message : "Could not create workspace.");
    }
  };

  return (
    <Card className="mx-auto max-w-lg">
      <CardHeader>
        <CardTitle>Create your workspace</CardTitle>
        <CardDescription>
          A workspace is one client business — its own agents, contacts, knowledge base and phone
          numbers, fully isolated from every other workspace.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div>
            <Label htmlFor="name">Business name</Label>
            <Input id="name" placeholder="Aaha Dental Care" {...register("name")} />
            <FieldError>{errors.name?.message}</FieldError>
          </div>
          <div>
            <Label htmlFor="slug">Workspace URL slug</Label>
            <Input id="slug" placeholder="aaha-dental" {...register("slug")} />
            <FieldError>{errors.slug?.message}</FieldError>
          </div>
          {formError ? <p className="text-sm text-danger">{formError}</p> : null}
          <Button type="submit" className="w-full" loading={isSubmitting}>
            Create workspace
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
